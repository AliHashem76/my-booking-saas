import datetime
import uvicorn
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# إعدادات قاعدة البيانات
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SQLALCHEMY_DATABASE_URL = DATABASE_URL if DATABASE_URL else "sqlite:///./saas.db"
connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# الجداول
class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String); slug = Column(String, unique=True, index=True)
    owner_phone = Column(String); password = Column(String)

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    name = Column(String); duration = Column(Integer); price = Column(Float)

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    service_id = Column(Integer, ForeignKey("services.id"))
    customer_name = Column(String); customer_phone = Column(String)
    booking_date = Column(Date); booking_time = Column(Time); status = Column(String, default="confirmed")

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# النماذج
class LoginReq(BaseModel): phone: str; password: str
class ServiceReq(BaseModel): business_id: int; name: str; duration: int; price: float
class BookingReq(BaseModel): business_id: int; service_id: int; customer_name: str; customer_phone: str; booking_date: str; booking_time: str

# الروابط
@app.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    b = db.query(Business).filter(Business.owner_phone == req.phone, Business.password == req.password).first()
    if not b: raise HTTPException(400)
    return {"business_id": b.id, "business_name": b.name}

# إضافة خدمة
@app.post("/add-service/")
def add_service(req: ServiceReq, db: Session = Depends(get_db)):
    s = Service(business_id=req.business_id, name=req.name, duration=req.duration, price=req.price)
    db.add(s); db.commit(); return {"status": "success"}

# تعديل خدمة (الجديد)
@app.put("/services/{service_id}")
def update_service(service_id: int, req: ServiceReq, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404)
    s.name = req.name; s.price = req.price; s.duration = req.duration
    db.commit()
    return {"status": "updated"}

# حذف خدمة
@app.delete("/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if s: db.delete(s); db.commit()
    return {"status": "deleted"}

# جلب الخدمات
@app.get("/business/{bid}/services")
def get_services(bid: int, db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.business_id == bid).all()

# جلب خدمات الزبون
@app.get("/shop/{slug}/services")
def get_shop_services(slug: str, db: Session = Depends(get_db)):
    bus = db.query(Business).filter(Business.slug == slug).first()
    if not bus: raise HTTPException(404)
    services = db.query(Service).filter(Service.business_id == bus.id).all()
    return {"shop_name": bus.name, "services": services, "business_id": bus.id}

# جلب الحجوزات مع التفاصيل الكاملة
@app.get("/business/{bid}/bookings")
def get_bookings(bid: int, db: Session = Depends(get_db)):
    res = db.query(Booking, Service).join(Service).filter(Booking.business_id == bid).order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).all()
    return [{
        "id":b.id, 
        "customer_name":b.customer_name, 
        "customer_phone": b.customer_phone, 
        "service_name":s.name, 
        "price": s.price,  # القيمة
        "booking_date":str(b.booking_date), 
        "booking_time":str(b.booking_time),
        "status": b.status
    } for b,s in res]

# إنشاء حجز (بدون واتساب)
@app.post("/book-appointment/")
def book(req: BookingReq, db: Session = Depends(get_db)):
    b_date = datetime.datetime.strptime(req.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(req.booking_time, "%H:%M").time()
    new_b = Booking(business_id=req.business_id, service_id=req.service_id, customer_name=req.customer_name, customer_phone=req.customer_phone, booking_date=b_date, booking_time=b_time)
    db.add(new_b); db.commit()
    return {"status": "success"}

# إلغاء حجز
@app.put("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if b: 
        b.status = "cancelled"
        db.commit()
    return {"status": "cancelled"}

# عرض الصفحات
@app.get("/login")
def gui_login(): return FileResponse('login.html')
@app.get("/admin")
def gui_admin(): return FileResponse('admin.html')
@app.get("/booking")
def gui_book(): return FileResponse('booking.html')
