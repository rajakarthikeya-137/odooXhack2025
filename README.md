# odooXhack2025

**📦 Inventory Management System (IMS)
FastAPI • MongoDB • TailwindCSS • Single-Page Frontend

A modern, full-stack Inventory Management System built using FastAPI (backend) and a single-page TailwindCSS frontend, featuring user authentication, RBAC, stock control, product cataloging, warehouse/location tracking, inward/outward operations, adjustments, and a complete user profile system with avatar upload.

⭐ Features
🔐 Authentication & User Security

Secure JWT login & signup

Password hashing (Bcrypt)

OTP-based password reset

Change password module

Activity logging

User profile with avatar upload

🗂️ Role-Based Access Control (RBAC)
Role	Access Level
STOCK_MASTER	Full access to all modules
INVENTORY_MANAGER	Products, Receipts, Deliveries
WAREHOUSE_STAFF	Stock, Adjustments, Transfers
📦 Inventory Features

Product master management

Warehouse & location creation

Goods Inward (Receipts)

Goods Outward (Deliveries)

Internal Transfers

Stock Adjustments

Real-time stock updates

Movement ledger with full audit

📊 Dashboard Analytics

Low stock indicator

Out-of-stock products

Pending receipts/deliveries/transfers

Recent movement preview

🧱 Tech Stack

Backend: FastAPI, MongoDB, JWT, Passlib
Frontend: HTML, TailwindCSS, Vanilla JS
Architecture: REST API + SPA
Database: MongoDB Atlas / Local

🏗️ Architecture Diagram
Frontend (HTML + JS SPA)
            |
            ▼
     FastAPI Backend
  Auth • Stock • Ledger • CRUD
            |
            ▼
      MongoDB Database
**
