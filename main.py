import datetime
import uvicorn
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# ==========================================
# 1. إعدادات قاعدة البيانات (الجزء الذكي 🧠)
# ==========================================

# نحاول جلب رابط قاعدة البيانات من إعدادات Render
DATABASE_URL = os.environ.get("DATABASE_URL")

# تصحيح الرابط لأن Render يعطيه بصيغة قديمة لا تحبها المكتبة الجديدة
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# إذا وجدنا رابط سحابي نستخدمه، وإلا نستخدم الملف المحلي
SQLALCHEMY_DATABASE_URL = DATABASE_URL if DATABASE_URL else "sqlite:///./saas.db"

# إعدادات الاتصال (تختلف قليلاً بين النوعين)
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

# إنشاء الجداول تلقائياً
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. إعدادات السيرفر
# ==========================================
app = FastAPI(title="SaaS Booking System")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# نماذج البيانات (Pydantic Models)
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

# دالة الاتصال بقاعدة البيانات (تم تصحيح الخطأ السابق هنا ✅)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. الروابط (APIs)
# ==========================================

# تسجيل الدخول
@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.owner_phone == request.phone).first()
    if not business or business.password != request.password: raise HTTPException(400, "Error")
    return {"status": "success", "business_id": business.id, "business_name": business.name}

# إنشاء بزنس جديد
@app.post("/create-business/")
def create_business(business: BusinessCreate, db: Session = Depends(get_db)):
    db_business = Business(name=business.name, slug=business.slug, owner_phone=business.owner_phone, password=business.password)
    db.add(db_business); db.commit(); return db_business

# إضافة خدمة
@app.post("/add-service/")
def add_service(service: ServiceCreate, db: Session = Depends(get_db)):
    db_service = Service(business_id=service.business_id, name=service.name, duration=service.duration, price=service.price)
    db.add(db_service); db.commit(); return {"message": "Added"}

# جلب خدمات بزنس معين (للأدمن)
@app.get("/business/{business_id}/services")
def get_business_services(business_id: int, db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.business_id == business_id).all()

# تعديل خدمة
@app.put("/services/{service_id}")
def update_service(service_id: int, service: ServiceUpdate, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404)
    s.name=service.name; s.duration=service.duration; s.price=service.price; db.commit(); return {"message": "Updated"}

# حذف خدمة
@app.delete("/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404);
    db.delete(s); db.commit(); return {"message": "Deleted"}

# جلب الخدمات لصفحة الزبون (Public)
@app.get("/shop/{slug}/services")
def get_shop_services(slug: str, db: Session = Depends(get_db)):
    b = db.query(Business).filter(Business.slug == slug).first()
    if not b: raise HTTPException(404)
    s = db.query(Service).filter(Service.business_id == b.id).all()
    return {"shop_name": b.name, "services": s}

# إنشاء حجز
@app.post("/book-appointment/")
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    b_date = datetime.datetime.strptime(booking.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(booking.booking_time, "%H:%M").time()
    
    # التحقق من أن التاريخ ليس في الماضي
    if b_date < datetime.date.today(): raise HTTPException(400, "Old Date")
    
    b = db.query(Business).filter(Business.id == booking.business_id).first()
    s = db.query(Service).filter(Service.id == booking.service_id).first()
    if not b or not s: raise HTTPException(404)

    new_booking = Booking(
        business_id=booking.business_id, 
        service_id=booking.service_id, 
        customer_name=booking.customer_name, 
        customer_phone=booking.customer_phone, 
        booking_date=b_date, 
        booking_time=b_time
    )
    db.add(new_booking)
    db.commit()
    print(f"🔔 حجز جديد: {booking.customer_name} في {b.name}")
    return {"status": "success"}

# عرض الحجوزات (للأدمن)
@app.get("/business/{business_id}/bookings")
def get_bookings(business_id: int, db: Session = Depends(get_db)):
    res = db.query(Booking, Service).join(Service, Booking.service_id == Service.id).filter(Booking.business_id == business_id).order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).all()
    return [{"id":b.id, "customer_name":b.customer_name, "customer_phone":b.customer_phone, "booking_date":b.booking_date, "booking_time":b.booking_time, "status":b.status, "service_name":s.name} for b,s in res]

# إلغاء حجز
@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b: raise HTTPException(404)
    b.status = "cancelled"; db.commit(); 
    return {"message": "Cancelled"}

# ==========================================
# 5. عرض ملفات HTML (Frontend) 🌍
# ==========================================
@app.get("/")
def read_index():
    return FileResponse('booking.html')

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
