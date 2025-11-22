# ==============================================
#  FULL INVENTORY MANAGEMENT SYSTEM - FASTAPI
#  (WITH PROFILE, RBAC, OTP, ACTIVITY TRACKING)
# ==============================================

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from bson import ObjectId
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import os
import shutil
import random
import string


# ---------------------------------------------------
# 1️⃣ CREATE FASTAPI APP
# ---------------------------------------------------
app = FastAPI(title="Inventory Management System - Single File")


# ---------------------------------------------------
# 2️⃣ ENABLE CORS
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------
# 3️⃣ CONFIG
# ---------------------------------------------------
SECRET_KEY = "verysecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


client = MongoClient(
    "mongodb+srv://karthikeya0090rk3021_db_user:123@cluster0.u0rcats.mongodb.net/ims?retryWrites=true&w=majority"
)
db = client["ims"]


# ---------------------------------------------------
# 4️⃣ UPLOADS FOLDER FOR AVATARS
# ---------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ---------------------------------------------------
# Utility – Fix ObjectId in MongoDB documents
# ---------------------------------------------------
def fix(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


# ---------------------------------------------------
# AUTH HELPERS
# ---------------------------------------------------
def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)


def create_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.users.find_one({"_id": ObjectId(payload.get("id"))})
        if not user:
            raise HTTPException(401, "Invalid user")
        return fix(user)
    except JWTError:
        raise HTTPException(401, "Invalid token")


# ---------------------------------------------------
# RBAC HELPER (ROLE-BASED ACCESS CONTROL)
# ---------------------------------------------------
def require_role(*roles):
    async def wrapper(user=Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(403, "Forbidden for this role")
        return user
    return wrapper


# ---------------------------------------------------
# ACTIVITY TRACKING HELPER
# ---------------------------------------------------
def log_activity(user_id: str, action: str, meta: Optional[dict] = None):
    db.activities.insert_one({
        "userId": user_id,
        "action": action,
        "meta": meta or {},
        "at": datetime.utcnow(),
    })


# ==============================================
#  Pydantic Models
# ==============================================

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "WAREHOUSE_STAFF"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    role: str
    avatarUrl: Optional[str] = None


class PasswordChange(BaseModel):
    oldPassword: str
    newPassword: str


class OTPRequest(BaseModel):
    email: str


class OTPVerify(BaseModel):
    email: str
    otp: str
    newPassword: str


class Product(BaseModel):
    name: str
    sku: str
    category: Optional[str] = None
    uom: str
    reorderPoint: int = 0
    reorderQty: int = 0


class Warehouse(BaseModel):
    name: str
    code: str
    address: Optional[str] = None


class Location(BaseModel):
    name: str
    code: str
    warehouse: str


class ReceiptLine(BaseModel):
    product: str
    location: str
    qtyOrdered: int
    qtyReceived: int


class Receipt(BaseModel):
    supplierName: Optional[str]
    docNumber: str
    warehouse: str
    lines: List[ReceiptLine]


class DeliveryLine(BaseModel):
    product: str
    fromLocation: str
    qtyPlanned: int
    qtyDelivered: int


class Delivery(BaseModel):
    customerName: Optional[str]
    docNumber: str
    warehouse: str
    lines: List[DeliveryLine]


class TransferLine(BaseModel):
    product: str
    fromLocation: str
    toLocation: str
    qty: int


class Transfer(BaseModel):
    fromWarehouse: str
    toWarehouse: str
    lines: List[TransferLine]


class AdjustmentLine(BaseModel):
    product: str
    location: str
    countedQty: int


class Adjustment(BaseModel):
    warehouse: str
    reason: Optional[str]
    lines: List[AdjustmentLine]


# ==============================================
# STOCK FUNCTIONS
# ==============================================

def update_stock(product, location, qty):
    db.stock.update_one(
        {"product": product, "location": location},
        {"$inc": {"qty": qty}},
        upsert=True,
    )


def add_ledger(product, fromLoc, toLoc, qty, type, ref, user):
    db.ledger.insert_one({
        "product": product,
        "fromLocation": fromLoc,
        "toLocation": toLoc,
        "qty": qty,
        "type": type,
        "reference": ref,
        "user": user,
        "at": datetime.utcnow(),
    })


# ==============================================
# AUTH ENDPOINTS
# ==============================================

@app.post("/signup", response_model=Token)
def signup(user: UserCreate):
    if db.users.find_one({"email": user.email}):
        raise HTTPException(400, "Email already exists")

    uid = db.users.insert_one({
        "name": user.name,
        "email": user.email,
        "password": hash_password(user.password),
        "role": user.role,
        "avatarUrl": None,
    }).inserted_id

    token = create_token({"id": str(uid)}, timedelta(days=7))
    log_activity(str(uid), "SIGNUP", {"email": user.email})
    return {"access_token": token}


@app.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = db.users.find_one({"email": form.username})
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")

    token = create_token({"id": str(user["_id"])}, timedelta(days=7))
    log_activity(str(user["_id"]), "LOGIN", {"email": user["email"]})
    return {"access_token": token}


# ==============================================
# PROFILE / ME / PASSWORD / AVATAR
# ==============================================

@app.get("/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    return UserPublic(
        id=user["id"],
        name=user.get("name", ""),
        email=user.get("email", ""),
        role=user.get("role", ""),
        avatarUrl=user.get("avatarUrl"),
    )


@app.post("/change-password")
async def change_password(data: PasswordChange, user=Depends(get_current_user)):
    db_user = db.users.find_one({"_id": ObjectId(user["id"])})

    if not db_user or not verify_password(data.oldPassword, db_user["password"]):
        raise HTTPException(400, "Old password incorrect")

    db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"password": hash_password(data.newPassword)}},
    )

    log_activity(user["id"], "CHANGE_PASSWORD", {})
    return {"message": "Password updated successfully"}


@app.post("/profile/avatar")
async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    ts = int(datetime.utcnow().timestamp())
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._-")
    filename = f"{user['id']}_{ts}_{safe_name}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    avatar_url = f"/uploads/{filename}"

    db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"avatarUrl": avatar_url}},
    )

    log_activity(user["id"], "UPLOAD_AVATAR", {"avatarUrl": avatar_url})
    return {"avatarUrl": avatar_url}


# ==============================================
# OTP RESET ENDPOINTS
# ==============================================

def generate_otp(length: int = 6):
    return "".join(random.choice(string.digits) for _ in range(length))


@app.post("/request-reset-otp")
async def request_reset_otp(data: OTPRequest):
    user = db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(404, "User not found")

    otp = generate_otp()
    expiry = datetime.utcnow() + timedelta(minutes=10)

    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"resetOtp": otp, "resetOtpExpiresAt": expiry}},
    )

    log_activity(str(user["_id"]), "REQUEST_RESET_OTP", {})
    return {"message": "OTP generated (demo only)", "otp": otp}


@app.post("/reset-password")
async def reset_password(data: OTPVerify):
    user = db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(404, "User not found")

    if user.get("resetOtp") != data.otp:
        raise HTTPException(400, "Invalid OTP")

    if user.get("resetOtpExpiresAt") < datetime.utcnow():
        raise HTTPException(400, "OTP expired")

    db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password": hash_password(data.newPassword)},
            "$unset": {"resetOtp": "", "resetOtpExpiresAt": ""},
        },
    )

    log_activity(str(user["_id"]), "RESET_PASSWORD", {})
    return {"message": "Password reset successful"}


# ==============================================
# PRODUCT ENDPOINTS (RBAC)
# ==============================================

@app.post("/products")
async def create_product(product: Product, user=Depends(require_role("STOCK_MASTER", "INVENTORY_MANAGER"))):
    db.products.insert_one(product.dict())
    log_activity(user["id"], "CREATE_PRODUCT", {"sku": product.sku})
    return {"message": "Product created"}


@app.get("/products")
async def list_products(user=Depends(get_current_user)):
    return [fix(x) for x in db.products.find()]


# ==============================================
# WAREHOUSE & LOCATION (RBAC)
# ==============================================

@app.post("/warehouses")
async def create_wh(wh: Warehouse, user=Depends(require_role("STOCK_MASTER"))):
    db.warehouses.insert_one(wh.dict())
    log_activity(user["id"], "CREATE_WAREHOUSE", {"code": wh.code})
    return {"message": "Warehouse created"}


@app.get("/warehouses")
async def get_wh(user=Depends(get_current_user)):
    return [fix(x) for x in db.warehouses.find()]


@app.post("/locations")
async def create_location(loc: Location, user=Depends(require_role("STOCK_MASTER"))):
    db.locations.insert_one(loc.dict())
    log_activity(user["id"], "CREATE_LOCATION", {"code": loc.code})
    return {"message": "Location created"}


@app.get("/locations")
async def get_locations(user=Depends(get_current_user)):
    return [fix(x) for x in db.locations.find()]


# ==============================================
# RECEIPTS
# ==============================================

@app.post("/receipts")
async def create_receipt(data: Receipt, user=Depends(get_current_user)):
    rid = db.receipts.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.location, line.qtyReceived)
        add_ledger(
            line.product,
            None,
            line.location,
            line.qtyReceived,
            "RECEIPT",
            str(rid),
            user["id"],
        )

    log_activity(user["id"], "CREATE_RECEIPT", {"docNumber": data.docNumber})
    return {"message": "Receipt processed", "id": str(rid)}


@app.get("/receipts")
async def list_receipts(user=Depends(get_current_user)):
    return [fix(x) for x in db.receipts.find()]


# ==============================================
# DELIVERIES
# ==============================================

@app.post("/deliveries")
async def create_delivery(data: Delivery, user=Depends(get_current_user)):
    did = db.deliveries.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.fromLocation, -line.qtyDelivered)
        add_ledger(
            line.product,
            line.fromLocation,
            None,
            line.qtyDelivered,
            "DELIVERY",
            str(did),
            user["id"],
        )

    log_activity(user["id"], "CREATE_DELIVERY", {"docNumber": data.docNumber})
    return {"message": "Delivery processed", "id": str(did)}


@app.get("/deliveries")
async def list_deliveries(user=Depends(get_current_user)):
    return [fix(x) for x in db.deliveries.find()]


# ==============================================
# TRANSFERS
# ==============================================

@app.post("/transfers")
async def transfer(data: Transfer, user=Depends(get_current_user)):
    tid = db.transfers.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.fromLocation, -line.qty)
        update_stock(line.product, line.toLocation, line.qty)
        add_ledger(
            line.product,
            line.fromLocation,
            line.toLocation,
            line.qty,
            "TRANSFER",
            str(tid),
            user["id"],
        )

    log_activity(user["id"], "CREATE_TRANSFER", {})
    return {"message": "Transfer completed", "id": str(tid)}


@app.get("/transfers")
async def list_transfers(user=Depends(get_current_user)):
    return [fix(x) for x in db.transfers.find()]


# ==============================================
# ADJUSTMENTS
# ==============================================

@app.post("/adjustments")
async def adjust(data: Adjustment, user=Depends(get_current_user)):
    aid = db.adjustments.insert_one(data.dict()).inserted_id

    for line in data.lines:
        rec = db.stock.find_one({"product": line.product, "location": line.location})
        curr = rec["qty"] if rec else 0

        diff = line.countedQty - curr

        if diff != 0:
            update_stock(line.product, line.location, diff)
            add_ledger(
                line.product,
                line.location if diff < 0 else None,
                line.location if diff > 0 else None,
                abs(diff),
                "ADJUSTMENT",
                str(aid),
                user["id"],
            )

    log_activity(user["id"], "CREATE_ADJUSTMENT", {"warehouse": data.warehouse})
    return {"message": "Adjustment applied", "id": str(aid)}


@app.get("/adjustments")
async def list_adjustments(user=Depends(get_current_user)):
    return [fix(x) for x in db.adjustments.find()]


# ==============================================
# STOCK & LEDGER
# ==============================================

@app.get("/stock")
async def stock(user=Depends(get_current_user)):
    return [fix(x) for x in db.stock.find()]


@app.get("/ledger")
async def ledger(user=Depends(get_current_user)):
    return [fix(x) for x in db.ledger.find().sort("at", -1)]


# ==============================================
# ACTIVITIES (MY LOG)
# ==============================================

@app.get("/activities/me")
async def my_activities(user=Depends(get_current_user)):
    docs = db.activities.find({"userId": user["id"]}).sort("at", -1)
    return [fix(x) for x in docs]


# ==============================================
# DASHBOARD
# ==============================================

@app.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    stock = list(db.stock.find())
    products = list(db.products.find())

    low = 0
    out = 0

    for p in products:
        qtys = [s["qty"] for s in stock if s["product"] == p["sku"]]
        total = sum(qtys) if qtys else 0

        if total == 0:
            out += 1
        elif total <= p.get("reorderPoint", 0):
            low += 1

    return {
        "lowStock": low,
        "outOfStock": out,
        "pendingReceipts": db.receipts.count_documents({}),
        "pendingDeliveries": db.deliveries.count_documents({}),
        "pendingTransfers": db.transfers.count_documents({}),
    }
