# ==============================================
#  FULL INVENTORY MANAGEMENT SYSTEM - FASTAPI
#  SINGLE FILE BACKEND (IMS)
# ==============================================

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import List, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from bson import ObjectId
from pymongo import MongoClient

# ==============================================
#  CONFIGURATION
# ==============================================

SECRET_KEY = "verysecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

client = MongoClient(
    "mongodb+srv://karthikeya0090rk3021_db_user:123@cluster0.u0rcats.mongodb.net/ims?retryWrites=true&w=majority&appName=Cluster0"
)

db = client["ims"]

app = FastAPI(title="Inventory Management System - Single File")

# ==============================================
#  UTILITY FUNCTIONS
# ==============================================

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.users.find_one({"_id": ObjectId(payload.get("id"))})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")
        user["id"] = str(user["_id"])
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

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

class Product(BaseModel):
    name: str
    sku: str
    category: str = None
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
# STOCK UTILITY FUNCTIONS
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
        "at": datetime.utcnow()
    })

# ==============================================
#  AUTH ENDPOINTS
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
    }).inserted_id

    token = create_token({"id": str(uid)}, timedelta(days=7))
    return {"access_token": token}

@app.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = db.users.find_one({"email": form.username})
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")

    token = create_token({"id": str(user["_id"])}, timedelta(days=7))
    return {"access_token": token}

# ==============================================
# PRODUCT ENDPOINTS
# ==============================================

@app.post("/products")
async def create_product(product: Product, user=Depends(get_current_user)):
    db.products.insert_one(product.dict())
    return {"message": "Product created"}

@app.get("/products")
async def list_products(user=Depends(get_current_user)):
    products = list(db.products.find())
    for p in products:
        p["id"] = str(p["_id"])
    return products

# ==============================================
# WAREHOUSE & LOCATION ENDPOINTS
# ==============================================

@app.post("/warehouses")
async def create_wh(wh: Warehouse, user=Depends(get_current_user)):
    db.warehouses.insert_one(wh.dict())
    return {"message": "Warehouse created"}

@app.get("/warehouses")
async def get_wh(user=Depends(get_current_user)):
    return list(db.warehouses.find())

@app.post("/locations")
async def create_location(loc: Location, user=Depends(get_current_user)):
    db.locations.insert_one(loc.dict())
    return {"message": "Location created"}

@app.get("/locations")
async def get_locations(user=Depends(get_current_user)):
    items = list(db.locations.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# RECEIPTS — INCOMING STOCK
# ==============================================

@app.post("/receipts")
async def create_receipt(data: Receipt, user=Depends(get_current_user)):
    rid = db.receipts.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.location, line.qtyReceived)
        add_ledger(line.product, None, line.location, line.qtyReceived,
                   "RECEIPT", str(rid), user["id"])

    return {"message": "Receipt processed", "id": str(rid)}

@app.get("/receipts")
async def list_receipts(user=Depends(get_current_user)):
    items = list(db.receipts.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# DELIVERIES — OUTGOING STOCK
# ==============================================

@app.post("/deliveries")
async def delivery(data: Delivery, user=Depends(get_current_user)):
    did = db.deliveries.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.fromLocation, -line.qtyDelivered)
        add_ledger(line.product, line.fromLocation, None, line.qtyDelivered,
                   "DELIVERY", str(did), user["id"])

    return {"message": "Delivery processed", "id": str(did)}

@app.get("/deliveries")
async def list_deliveries(user=Depends(get_current_user)):
    items = list(db.deliveries.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# INTERNAL TRANSFERS
# ==============================================

@app.post("/transfers")
async def transfer(data: Transfer, user=Depends(get_current_user)):
    tid = db.transfers.insert_one(data.dict()).inserted_id

    for line in data.lines:
        update_stock(line.product, line.fromLocation, -line.qty)
        update_stock(line.product, line.toLocation, line.qty)
        add_ledger(line.product, line.fromLocation, line.toLocation,
                   line.qty, "TRANSFER", str(tid), user["id"])

    return {"message": "Transfer completed", "id": str(tid)}

@app.get("/transfers")
async def list_transfers(user=Depends(get_current_user)):
    items = list(db.transfers.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# STOCK ADJUSTMENTS
# ==============================================

@app.post("/adjustments")
async def adjust(data: Adjustment, user=Depends(get_current_user)):
    aid = db.adjustments.insert_one(data.dict()).inserted_id

    for line in data.lines:
        record = db.stock.find_one({"product": line.product, "location": line.location})
        curr = record["qty"] if record else 0
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
                user["id"]
            )

    return {"message": "Adjustment applied", "id": str(aid)}

@app.get("/adjustments")
async def list_adjustments(user=Depends(get_current_user)):
    items = list(db.adjustments.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# STOCK AND LEDGER QUERIES
# ==============================================

@app.get("/stock")
async def stock(user=Depends(get_current_user)):
    items = list(db.stock.find())
    for x in items:
        x["id"] = str(x["_id"])
    return items

@app.get("/ledger")
async def ledger(user=Depends(get_current_user)):
    items = list(db.ledger.find().sort("at", -1))
    for x in items:
        x["id"] = str(x["_id"])
    return items

# ==============================================
# DASHBOARD KPIs
# ==============================================

@app.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):

    stock = list(db.stock.find())
    products = list(db.products.find())

    low = 0
    out = 0

    for p in products:
        levels = [s["qty"] for s in stock if s["product"] == p["sku"]]
        total = sum(levels) if levels else 0

        if total == 0:
            out += 1
        elif total <= p.get("reorderPoint", 0):
            low += 1

    pending_receipts = db.receipts.count_documents({})
    pending_deliveries = db.deliveries.count_documents({})
    pending_transfers = db.transfers.count_documents({})

    return {
        "lowStock": low,
        "outOfStock": out,
        "pendingReceipts": pending_receipts,
        "pendingDeliveries": pending_deliveries,
        "pendingTransfers": pending_transfers
    }
