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

# إعدادات قاعدة البيانات (PostgreSQL)
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

# دالة الواتساب
def send_whatsapp(mobile, message):
    INSTANCE_ID = "instance160055" 
    TOKEN = "zhuhv62xrig7fziq"
    url = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"
    payload = {"token": TOKEN, "to": mobile, "body": message}
    try: requests.post(url, data=payload, headers={'content-type': 'application/x-www-form-urlencoded'})
    except: print("WhatsApp Error")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class LoginReq(BaseModel): phone: str; password: str
class ServiceReq(BaseModel): business_id: int; name: str; duration: int; price: float
class BookingReq(BaseModel): business_id: int; service_id: int; customer_name: str; customer_phone: str; booking_date: str; booking_time: str

@app.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    b = db.query(Business).filter(Business.owner_phone == req.phone, Business.password == req.password).first()
    if not b: raise HTTPException(400)
    return {"business_id": b.id, "business_name": b.name}

@app.post("/add-service/")
def add_service(req: ServiceReq, db: Session = Depends(get_db)):
    s = Service(business_id=req.business_id, name=req.name, duration=req.duration, price=req.price)
    db.add(s); db.commit(); return {"status": "success"}

@app.get("/business/{bid}/services")
def get_services(bid: int, db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.business_id == bid).all()

@app.get("/business/{bid}/bookings")
def get_bookings(bid: int, db: Session = Depends(get_db)):
    res = db.query(Booking, Service).join(Service).filter(Booking.business_id == bid).all()
    return [{"id":b.id, "customer_name":b.customer_name, "customer_phone": b.customer_phone, "service_name":s.name, "booking_date":str(b.booking_date), "booking_time":str(b.booking_time), "status":b.status} for b,s in res]

@app.post("/book-appointment/")
def book(req: BookingReq, db: Session = Depends(get_db)):
    b_date = datetime.datetime.strptime(req.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(req.booking_time, "%H:%M").time()
    new_b = Booking(business_id=req.business_id, service_id=req.service_id, customer_name=req.customer_name, customer_phone=req.customer_phone, booking_date=b_date, booking_time=b_time)
    db.add(new_b); db.commit()
    return {"status": "success"}

@app.get("/login")
def gui_login(): return FileResponse('login.html')
@app.get("/admin")
def gui_admin(): return FileResponse('admin.html')
@app.get("/booking")
def gui_book(): return FileResponse('booking.html')
