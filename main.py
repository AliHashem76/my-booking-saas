import datetime
import requests
import uvicorn
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# ==========================================
# 1. إعدادات ULTRAMSG
# ==========================================
ULTRAMSG_INSTANCE_ID = "instanceXXXXX"
ULTRAMSG_TOKEN = "tokenXXXXX"

def send_whatsapp(mobile, message):
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
    payload = { "token": ULTRAMSG_TOKEN, "to": mobile, "body": message }
    try:
        # requests.post(url, data=payload) 
        print(f"📩 WhatsApp Simulated to {mobile}: {message}") 
    except Exception as e:
        print(f"❌ WhatsApp Error: {e}")

# ==========================================
# 2. إعدادات قاعدة البيانات
# ==========================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./saas.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
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
# 3. إعدادات السيرفر
# ==========================================
app = FastAPI(title="SaaS Booking System")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class BusinessCreate(BaseModel):
    name: str; slug: str; owner_phone: str; password: str
class LoginRequest(BaseModel):
    phone: str; password: str
class ServiceCreate(BaseModel):
    business_id: int; name: str; duration: int; price: float
class ServiceUpdate(BaseModel):
    name: str; duration: int; price: float
class BookingCreate(BaseModel):
    business_id: int; service_id: int; customer_name: str; customer_phone: str; booking_date: str; booking_time: str

def get_db():
    db = SessionLocal(); try: yield db; finally: db.close()

# ==========================================
# 4. الروابط (APIs)
# ==========================================
@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.owner_phone == request.phone).first()
    if not business or business.password != request.password: raise HTTPException(400, "Error")
    return {"status": "success", "business_id": business.id, "business_name": business.name}

@app.post("/create-business/")
def create_business(business: BusinessCreate, db: Session = Depends(get_db)):
    db_business = Business(name=business.name, slug=business.slug, owner_phone=business.owner_phone, password=business.password)
    db.add(db_business); db.commit(); return db_business

@app.post("/add-service/")
def add_service(service: ServiceCreate, db: Session = Depends(get_db)):
    db_service = Service(business_id=service.business_id, name=service.name, duration=service.duration, price=service.price)
    db.add(db_service); db.commit(); return {"message": "Added"}

@app.get("/business/{business_id}/services")
def get_business_services(business_id: int, db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.business_id == business_id).all()

@app.put("/services/{service_id}")
def update_service(service_id: int, service: ServiceUpdate, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404)
    s.name=service.name; s.duration=service.duration; s.price=service.price; db.commit(); return {"message": "Updated"}

@app.delete("/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404);
    db.delete(s); db.commit(); return {"message": "Deleted"}

@app.get("/shop/{slug}/services")
def get_shop_services(slug: str, db: Session = Depends(get_db)):
    b = db.query(Business).filter(Business.slug == slug).first()
    if not b: raise HTTPException(404)
    s = db.query(Service).filter(Service.business_id == b.id).all()
    return {"shop_name": b.name, "services": s}

@app.post("/book-appointment/")
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    b_date = datetime.datetime.strptime(booking.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(booking.booking_time, "%H:%M").time()
    if b_date < datetime.date.today(): raise HTTPException(400, "Old Date")
    
    b = db.query(Business).filter(Business.id == booking.business_id).first()
    s = db.query(Service).filter(Service.id == booking.service_id).first()
    if not b or not s: raise HTTPException(404)

    new_booking = Booking(business_id=booking.business_id, service_id=booking.service_id, customer_name=booking.customer_name, customer_phone=booking.customer_phone, booking_date=b_date, booking_time=b_time)
    db.add(new_booking); db.commit()
    send_whatsapp(b.owner_phone, f"🔔 حجز: {booking.customer_name}"); send_whatsapp(booking.customer_phone, "تم الحجز")
    return {"status": "success"}

@app.get("/business/{business_id}/bookings")
def get_bookings(business_id: int, db: Session = Depends(get_db)):
    res = db.query(Booking, Service).join(Service, Booking.service_id == Service.id).filter(Booking.business_id == business_id).order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).all()
    return [{"id":b.id, "customer_name":b.customer_name, "customer_phone":b.customer_phone, "booking_date":b.booking_date, "booking_time":b.booking_time, "status":b.status, "service_name":s.name} for b,s in res]

@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b: raise HTTPException(404)
    b.status = "cancelled"; db.commit(); send_whatsapp(b.customer_phone, "تم الإلغاء"); return {"message": "Cancelled"}

# ==========================================
# 5. عرض الصفحات (Frontend Serving) 🌍
# ==========================================
@app.get("/")
def read_index():
    return FileResponse('booking.html') # الصفحة الرئيسية هي الحجز

@app.get("/booking")
def read_booking():
    return FileResponse('booking.html')

@app.get("/admin")
def read_admin():
    return FileResponse('admin.html')

@app.get("/login")
def read_login():
    return FileResponse('login.html')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
