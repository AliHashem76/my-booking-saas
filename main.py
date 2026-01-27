import datetime
import uvicorn
import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, Float
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# ==========================================
# 1. إعدادات قاعدة البيانات (Database Config)
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
# تصحيح رابط Render ليعمل مع مكتبات بايثون الحديثة
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# استخدام SQLite كبديل محلي إذا لم نكن على السيرفر
SQLALCHEMY_DATABASE_URL = DATABASE_URL if DATABASE_URL else "sqlite:///./saas.db"
connect_args = {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. جداول البيانات (Database Models)
# ==========================================
class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    slug = Column(String, unique=True, index=True) # الرابط المميز (مثل: ali-salon)
    owner_phone = Column(String)
    password = Column(String)

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    name = Column(String)
    duration = Column(Integer) # بالدقائق
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
    status = Column(String, default="confirmed") # confirmed, cancelled

# إنشاء الجداول عند البدء
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. إعدادات التطبيق (App Setup)
# ==========================================
app = FastAPI(title="SaaS Booking System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# نماذج البيانات (Pydantic Schemas)
class LoginReq(BaseModel):
    phone: str
    password: str

class ServiceReq(BaseModel):
    business_id: int
    name: str
    duration: int
    price: float

class BookingReq(BaseModel):
    business_id: int
    service_id: int
    customer_name: str
    customer_phone: str
    booking_date: str
    booking_time: str

# نماذج السوبر أدمن
class BusinessUpdate(BaseModel):
    name: str
    owner_phone: str
    password: str

class BusinessCreate(BaseModel):
    name: str
    slug: str
    owner_phone: str
    password: str

# دالة الاتصال بالقاعدة
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. الروابط العامة (Public & Business Admin)
# ==========================================

# --- تسجيل الدخول لأصحاب المحلات ---
@app.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    b = db.query(Business).filter(Business.owner_phone == req.phone, Business.password == req.password).first()
    if not b:
        raise HTTPException(status_code=400, detail="بيانات الدخول غير صحيحة")
    return {"status": "success", "business_id": b.id, "business_name": b.name}

# --- إدارة الخدمات (إضافة - تعديل - حذف) ---
@app.post("/add-service/")
def add_service(req: ServiceReq, db: Session = Depends(get_db)):
    s = Service(business_id=req.business_id, name=req.name, duration=req.duration, price=req.price)
    db.add(s)
    db.commit()
    return {"status": "success"}

@app.put("/services/{service_id}")
def update_service(service_id: int, req: ServiceReq, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if not s: raise HTTPException(404)
    s.name = req.name
    s.price = req.price
    s.duration = req.duration
    db.commit()
    return {"status": "updated"}

@app.delete("/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    s = db.query(Service).filter(Service.id == service_id).first()
    if s:
        db.delete(s)
        db.commit()
    return {"status": "deleted"}

# جلب الخدمات (للأدمن)
@app.get("/business/{bid}/services")
def get_services(bid: int, db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.business_id == bid).all()

# جلب الخدمات (للزبون عبر الرابط Slug)
@app.get("/shop/{slug}/services")
def get_shop_services(slug: str, db: Session = Depends(get_db)):
    bus = db.query(Business).filter(Business.slug == slug).first()
    if not bus:
        raise HTTPException(status_code=404, detail="المتجر غير موجود")
    services = db.query(Service).filter(Service.business_id == bus.id).all()
    return {"shop_name": bus.name, "services": services, "business_id": bus.id}

# --- إدارة الحجوزات ---
@app.get("/business/{bid}/bookings")
def get_bookings(bid: int, db: Session = Depends(get_db)):
    # جلب الحجوزات مع تفاصيل الخدمة (السعر والاسم)
    res = db.query(Booking, Service).join(Service).filter(Booking.business_id == bid).order_by(Booking.booking_date.desc(), Booking.booking_time.desc()).all()
    
    return [{
        "id": b.id,
        "customer_name": b.customer_name,
        "customer_phone": b.customer_phone,
        "service_name": s.name,
        "price": s.price,
        "booking_date": str(b.booking_date),
        "booking_time": str(b.booking_time),
        "status": b.status
    } for b, s in res]

@app.post("/book-appointment/")
def book(req: BookingReq, db: Session = Depends(get_db)):
    # تحويل النصوص إلى تواريخ
    b_date = datetime.datetime.strptime(req.booking_date, "%Y-%m-%d").date()
    b_time = datetime.datetime.strptime(req.booking_time, "%H:%M").time()
    
    new_b = Booking(
        business_id=req.business_id,
        service_id=req.service_id,
        customer_name=req.customer_name,
        customer_phone=req.customer_phone,
        booking_date=b_date,
        booking_time=b_time
    )
    db.add(new_b)
    db.commit()
    return {"status": "success"}

@app.put("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if b:
        b.status = "cancelled"
        db.commit()
    return {"status": "cancelled"}

# ==========================================
# 5. السوبر أدمن (Super Admin) - المنطقة المحمية 🛡️
# ==========================================

MASTER_KEY = "1,l/1D!8vfQ1C%!ZL@$dS/V!kbZp7uX:"  # 🔑 مفتاح الأمان (يمكنك تغييره)

# دالة التحقق من المفتاح
def verify_super(x_super_token: str = Header(None)):
    if x_super_token != MASTER_KEY:
        raise HTTPException(status_code=401, detail="غير مصرح بالدخول (مفتاح خاطئ)")

# 1. عرض كل المحلات
@app.get("/api/super/businesses")
def get_all_businesses(db: Session = Depends(get_db), authorized: bool = Depends(verify_super)):
    return db.query(Business).all()

# 2. إنشاء محل جديد (الطلب الجديد)
@app.post("/api/super/businesses")
def create_business_super(req: BusinessCreate, db: Session = Depends(get_db), authorized: bool = Depends(verify_super)):
    # التأكد من عدم تكرار الرابط (Slug)
    existing = db.query(Business).filter(Business.slug == req.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="هذا الرابط (Slug) مستخدم من قبل")
    
    new_b = Business(
        name=req.name,
        slug=req.slug,
        owner_phone=req.owner_phone,
        password=req.password
    )
    db.add(new_b)
    db.commit()
    return {"status": "created", "id": new_b.id}

# 3. حذف محل بالكامل
@app.delete("/api/super/businesses/{bid}")
def delete_business_super(bid: int, db: Session = Depends(get_db), authorized: bool = Depends(verify_super)):
    # تنظيف شامل: حذف الحجوزات والخدمات التابعة للمحل أولاً
    db.query(Booking).filter(Booking.business_id == bid).delete()
    db.query(Service).filter(Service.business_id == bid).delete()
    
    # حذف المحل
    b = db.query(Business).filter(Business.id == bid).first()
    if b:
        db.delete(b)
        db.commit()
    return {"status": "deleted"}

# 4. تعديل بيانات محل
@app.put("/api/super/businesses/{bid}")
def update_business_super(bid: int, req: BusinessUpdate, db: Session = Depends(get_db), authorized: bool = Depends(verify_super)):
    b = db.query(Business).filter(Business.id == bid).first()
    if not b: raise HTTPException(404)
    b.name = req.name
    b.owner_phone = req.owner_phone
    b.password = req.password
    db.commit()
    return {"status": "updated"}

# ==========================================
# 6. عرض صفحات HTML
# ==========================================
@app.get("/")
def read_root(): return FileResponse('login.html')

@app.get("/login")
def read_login(): return FileResponse('login.html')

@app.get("/admin")
def read_admin(): return FileResponse('admin.html')

@app.get("/booking")
def read_booking(): return FileResponse('booking.html')

@app.get("/super-login")
def read_super_login(): return FileResponse('super_login.html')

@app.get("/super-admin")
def read_super_admin(): return FileResponse('super_admin.html')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
