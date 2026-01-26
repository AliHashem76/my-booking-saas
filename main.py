import datetime
import uvicorn
import os
import requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# ==========================================
# 1. إعدادات قاعدة البيانات والاتصال
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SQLALCHEMY_DATABASE_URL = DATABASE_URL if DATABASE_URL else "sqlite:///./saas.db"
connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. الجداول (Models)
# ==========================================
class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    slug = Column(String, unique=True, index=True)
    owner_phone = Column(String)
    password = Column(String)

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    name = Column(String)
    duration = Column(Integer)
    price = Column(Float)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String)
    customer_phone = Column(String)
    booking_date = Column(Date)
    booking_time = Column(Time)
    status = Column(String, default="confirmed")

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. دالة إرسال الواتساب (UltraMsg)
# ==========================================
def send_whatsapp(mobile, message):
    # 👇 ضع بيانات UltraMsg الخاصة بك هنا
    INSTANCE_ID = "instance160055" 
    TOKEN = "zhuhv62xrig7fziq"
    
    url = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"
    payload = {
        "token": TOKEN,
        "to": mobile,
        "body": message
    }
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    try:
        response = requests.post(url, data=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ WhatsApp Error: {e}")
        return None

# ==========================================
# 4. إعدادات FastAPI والنماذج
# ==========================================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class BusinessCreate(BaseModel):
    name: str; slug: str; owner_phone: str; password: str
class LoginRequest(BaseModel):
    phone: str; password: str
class BookingCreate(BaseModel):
    business_id: int; service_id: int; customer_name: str; customer_phone: str; booking_date: str; booking_time: str

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ==========================================
# 5. الروابط (APIs)
# ==========================================

@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    bus = db.query(Business).filter(Business.owner_phone == request.phone).first()
    if not bus or bus.password != request.password: raise HTTPException(400, "خطأ في البيانات")
    return {"status": "success", "business_id": bus.id, "business_name": bus.name}

@app.post("/create-business/")
def create_business(bus: BusinessCreate, db: Session = Depends(get_db)):
    new_bus = Business(name=bus.name, slug=bus.slug, owner_phone=bus.owner_phone, password=bus.password)
    db.add(new_bus); db.commit(); return new_bus

@app.post("/book-appointment/")
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    b_date = datetime.datetime.strptime(booking.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(booking.booking_time, "%H:%M").time()
    
    bus = db.query(Business).filter(Business.id == booking.business_id).first()
    ser = db.query(Service).filter(Service.id == booking.service_id).first()
    
    if not bus or not ser: raise HTTPException(404, "المحل غير موجود")

    new_booking = Booking(
        business_id=booking.business_id, service_id=booking.service_id,
        customer_name=booking.customer_name, customer_phone=booking.customer_phone,
        booking_date=b_date, booking_time=b_time
    )
    db.add(new_booking); db.commit()

    # --- إرسال التنبيهات ---
    # لصاحب المحل
    owner_msg = f"🔔 *حجز جديد*\n👤 الزبون: {booking.customer_name}\n✂️ الخدمة: {ser.name}\n📅 التاريخ: {booking.booking_date}\n⏰ الوقت: {booking.booking_time}\n📱 رقم الزبون: {booking.customer_phone}"
    send_whatsapp(bus.owner_phone, owner_msg)

    # للزبون
    cust_msg = f"مرحباً {booking.customer_name}، تم تأكيد حجزك في *{bus.name}* بنجاح.\n📅 الموعد: {booking.booking_date} الساعة {booking.booking_time}."
    send_whatsapp(booking.customer_phone, cust_msg)

    return {"status": "success"}

# عرض الصفحات
@app.get("/booking")
def read_booking(): return FileResponse('booking.html')
@app.get("/admin")
def read_admin(): return FileResponse('admin.html')
@app.get("/login")
def read_login(): return FileResponse('login.html')

# (أضف باقي روابط الخدمات هنا كما في الكود السابق...)
