from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from bson import ObjectId
from src.models.db import db
from typing import Optional
import uuid

router = APIRouter()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class UserRegisterModel(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = Field(pattern="^(tenant|landlord)$")

class UserLoginModel(BaseModel):
    email: EmailStr
    password: str

class UserUpdateModel(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None

class UserModelOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    created_at: datetime
    phone: Optional[str] = None
    bio: Optional[str] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def serialize_user(user: dict) -> dict:
    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
    user.pop("session_token", None)
    return user

async def validate_token(user_id: str, token: str):
    """Validate that the session token belongs to the user_id."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    user = await db.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("session_token") != token:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing session token")
    return user

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegisterModel):
    existing_user = await db.db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = {
        "name": user.name,
        "email": user.email,
        "password_hash": user.password,  # Replace with bcrypt in production
        "role": user.role,
        "created_at": datetime.utcnow(),
        "session_token": None,
    }
    result = await db.db.users.insert_one(new_user)
    return {"message": "User registered successfully", "user_id": str(result.inserted_id)}

@router.post("/login")
async def login_user(user: UserLoginModel):
    db_user = await db.db.users.find_one({"email": user.email})
    if not db_user or db_user.get("password_hash") != user.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate and persist a session token
    token = str(uuid.uuid4())
    await db.db.users.update_one(
        {"_id": db_user["_id"]},
        {"$set": {"session_token": token}}
    )
    serialized = serialize_user(db_user)
    return {"message": "Login successful", "user": serialized, "session_token": token}

@router.post("/logout")
async def logout_user(x_user_id: str = Header(...), x_session_token: str = Header(...)):
    await validate_token(x_user_id, x_session_token)
    await db.db.users.update_one(
        {"_id": ObjectId(x_user_id)},
        {"$set": {"session_token": None}}
    )
    return {"message": "Logged out successfully"}

@router.get("/{user_id}", response_model=UserModelOut)
async def get_user(user_id: str):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid User ID format")
    user = await db.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return serialize_user(user)

@router.put("/{user_id}", response_model=UserModelOut)
async def update_user(
    user_id: str,
    update_data: UserUpdateModel,
    x_session_token: str = Header(..., description="Session token returned at login"),
):
    """Update profile. Requires the session token issued at login."""
    await validate_token(user_id, x_session_token)

    update_fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_fields}
    )
    updated_user = await db.db.users.find_one({"_id": ObjectId(user_id)})
    return serialize_user(updated_user)
