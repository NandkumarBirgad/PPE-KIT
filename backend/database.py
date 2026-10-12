import datetime
from werkzeug.security import generate_password_hash
from config import Config

db_client = None
db_instance = None
is_mongo_connected = False

# In-memory storage fallback collections
mem_users = []
mem_zones = []
mem_detections = []
mem_notifications = []

def init_db():
    global db_client, db_instance, is_mongo_connected
    try:
        from pymongo import MongoClient
        db_client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=2500)
        # Test connection
        db_client.server_info()
        db_instance = db_client[Config.DB_NAME]
        is_mongo_connected = True
        print(f"📦 MongoDB connected successfully to database: {Config.DB_NAME}")
    except Exception as e:
        is_mongo_connected = False
        print(f"⚠️ MongoDB connection notice: {e}")
        print("ℹ️ Operating with in-process resilient collection store.")
    
    seed_defaults()

def get_db():
    return db_instance

def get_status():
    return is_mongo_connected

def seed_defaults():
    # 1. Seed Admin & Reviewer
    admin_data = {
        "name": "System Safety Administrator",
        "email": "admin@ppe.com",
        "password_hash": generate_password_hash("Admin@123"),
        "role": "admin",
        "active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    reviewer_data = {
        "name": "Compliance Inspector Dave",
        "email": "reviewer@ppe.com",
        "password_hash": generate_password_hash("Reviewer@123"),
        "role": "reviewer",
        "active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    
    default_zones = [
        {
            "_id": "zone_01",
            "name": "Heavy Assembly Bay 01",
            "code": "BAY-01",
            "description": "Primary structural assembly and fabrication zone. Overhead crane hazards.",
            "requiredPPE": ["helmet", "vest", "boots"],
            "supervisor": {
                "name": "Vikram Patil",
                "email": "vikram.patil@ppe.com",
                "phone": "+91 98234 56789",
                "alertChannel": "WhatsApp & SMS",
                "shift": "Morning (08:00 - 16:00)"
            },
            "cameraFeed": {
                "name": "Bay 01 Primary HD Cam",
                "sourceType": "webcam",
                "streamUrl": "rtsp://192.168.1.101/live",
                "deviceId": "cam_01"
            },
            "buzzerEnabled": True,
            "buzzerSound": "siren",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "zone_02",
            "name": "Chemical & Paint Processing",
            "code": "CHEM-02",
            "description": "Volatile solvents, spray booths and chemical handling area.",
            "requiredPPE": ["goggles", "mask", "gloves", "vest"],
            "supervisor": {
                "name": "Pooja Kulkarni",
                "email": "pooja.kulkarni@ppe.com",
                "phone": "+91 98220 11223",
                "alertChannel": "Email & SMS",
                "shift": "General (09:00 - 18:00)"
            },
            "cameraFeed": {
                "name": "Chemical Line Cam 02",
                "sourceType": "ip_camera",
                "streamUrl": "rtsp://192.168.1.102/live",
                "deviceId": "cam_02"
            },
            "buzzerEnabled": True,
            "buzzerSound": "horn",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "zone_03",
            "name": "General Construction Deck",
            "code": "CONST-03",
            "description": "Multi-level scaffolding, civil engineering and material deck.",
            "requiredPPE": ["helmet", "vest", "gloves"],
            "supervisor": {
                "name": "Sachin Deshmukh",
                "email": "sachin.deshmukh@ppe.com",
                "phone": "+91 98211 44556",
                "alertChannel": "SMS & In-App",
                "shift": "Night (16:00 - 00:00)"
            },
            "cameraFeed": {
                "name": "Scaffold Deck Cam 03",
                "sourceType": "webcam",
                "streamUrl": "rtsp://192.168.1.103/live",
                "deviceId": "cam_03"
            },
            "buzzerEnabled": False,
            "buzzerSound": "beep",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
    ]

    if is_mongo_connected and db_instance is not None:
        try:
            users_col = db_instance["users"]
            if not users_col.find_one({"email": "admin@ppe.com"}):
                users_col.insert_one(admin_data)
                print("✅ Seeded default Admin user in MongoDB: admin@ppe.com")
            if not users_col.find_one({"email": "reviewer@ppe.com"}):
                users_col.insert_one(reviewer_data)
                print("✅ Seeded default Reviewer user in MongoDB: reviewer@ppe.com")
            
            zones_col = db_instance["zones"]
            if zones_col.count_documents({}) == 0:
                zones_col.insert_many(default_zones)
                print("✅ Seeded 3 default facility zones with supervisor & buzzer configs in MongoDB")
            else:
                # Update existing zones if supervisor is missing
                for dz in default_zones:
                    zones_col.update_one(
                        {"code": dz["code"]},
                        {"$set": {
                            "supervisor": dz["supervisor"],
                            "cameraFeed": dz["cameraFeed"],
                            "buzzerEnabled": dz["buzzerEnabled"],
                            "buzzerSound": dz["buzzerSound"]
                        }}
                    )
        except Exception as e:
            print(f"⚠️ Seeding warning: {e}")
    else:
        # Seed in-memory
        if not any(u["email"] == "admin@ppe.com" for u in mem_users):
            mem_users.append({"_id": "usr_admin", **admin_data})
        if not any(u["email"] == "reviewer@ppe.com" for u in mem_users):
            mem_users.append({"_id": "usr_reviewer", **reviewer_data})
        if len(mem_zones) == 0:
            mem_zones.extend(default_zones)
        else:
            for idx, z in enumerate(mem_zones):
                for dz in default_zones:
                    if z.get("code") == dz["code"]:
                        if "supervisor" not in z:
                            mem_zones[idx]["supervisor"] = dz["supervisor"]
                        if "cameraFeed" not in z:
                            mem_zones[idx]["cameraFeed"] = dz["cameraFeed"]
                        if "buzzerEnabled" not in z:
                            mem_zones[idx]["buzzerEnabled"] = dz["buzzerEnabled"]
                        if "buzzerSound" not in z:
                            mem_zones[idx]["buzzerSound"] = dz["buzzerSound"]

# Safe collections accessor
def get_users_col():
    if is_mongo_connected and db_instance is not None:
        return db_instance["users"]
    return None

def get_zones_col():
    if is_mongo_connected and db_instance is not None:
        return db_instance["zones"]
    return None

def get_detections_col():
    if is_mongo_connected and db_instance is not None:
        return db_instance["detections"]
    return None

def get_notifications_col():
    if is_mongo_connected and db_instance is not None:
        return db_instance["notifications"]
    return None
