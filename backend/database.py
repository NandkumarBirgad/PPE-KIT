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
mem_cameras = []

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
    # 1. Seed Super Admin & Zone Supervisors
    default_users = [
        {
            "_id": "usr_admin",
            "name": "System Safety Administrator",
            "email": "admin@ppe.com",
            "password_hash": generate_password_hash("Admin@123"),
            "role": "SUPER_ADMIN",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "usr_sup1",
            "name": "Vikram Patil",
            "email": "supervisor@ppe.com",
            "password_hash": generate_password_hash("Supervisor@123"),
            "role": "ZONE_SUPERVISOR",
            "assignedZoneId": "zone_01",
            "assignedZoneName": "Heavy Assembly Bay 01",
            "phone": "+91 98234 56789",
            "shift": "Morning (08:00 - 16:00)",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "usr_sup2",
            "name": "Pooja Kulkarni",
            "email": "pooja@ppe.com",
            "password_hash": generate_password_hash("Supervisor@123"),
            "role": "ZONE_SUPERVISOR",
            "assignedZoneId": "zone_02",
            "assignedZoneName": "Chemical & Paint Processing",
            "phone": "+91 98220 11223",
            "shift": "General (09:00 - 18:00)",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "usr_reviewer",
            "name": "Compliance Inspector Dave",
            "email": "reviewer@ppe.com",
            "password_hash": generate_password_hash("Reviewer@123"),
            "role": "ZONE_SUPERVISOR",
            "assignedZoneId": "zone_03",
            "assignedZoneName": "General Construction Deck",
            "phone": "+91 98211 44556",
            "shift": "Night (16:00 - 00:00)",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
    ]
    
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

    default_cameras = [
        {
            "_id": "cam_01",
            "name": "Bay 01 Primary HD Cam",
            "zoneId": "zone_01",
            "zoneName": "Heavy Assembly Bay 01",
            "status": "ONLINE",
            "sourceType": "webcam",
            "streamUrl": "rtsp://192.168.1.101/live",
            "resolution": "1080p HD",
            "fps": 25,
            "location": "Heavy Fabrication Deck",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "cam_02",
            "name": "Chemical Line Cam 02",
            "zoneId": "zone_02",
            "zoneName": "Chemical & Paint Processing",
            "status": "ONLINE",
            "sourceType": "ip_camera",
            "streamUrl": "rtsp://192.168.1.102/live",
            "resolution": "1080p HD",
            "fps": 30,
            "location": "Solvents & Spray Booths",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "cam_03",
            "name": "Scaffold Deck Cam 03",
            "zoneId": "zone_03",
            "zoneName": "General Construction Deck",
            "status": "ONLINE",
            "sourceType": "webcam",
            "streamUrl": "rtsp://192.168.1.103/live",
            "resolution": "720p HD",
            "fps": 25,
            "location": "Civil Engineering Deck",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        },
        {
            "_id": "cam_04",
            "name": "Gate 4 Logistics & Perimeter Cam",
            "zoneId": "zone_01",
            "zoneName": "Heavy Assembly Bay 01",
            "status": "OFFLINE",
            "sourceType": "cctv_nvr",
            "streamUrl": "rtsp://192.168.1.104/live",
            "resolution": "1080p HD",
            "fps": 20,
            "location": "Perimeter Gate 4",
            "active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
    ]

    if is_mongo_connected and db_instance is not None:
        try:
            users_col = db_instance["users"]
            for du in default_users:
                existing = users_col.find_one({"email": du["email"]})
                if not existing:
                    users_col.insert_one(dict(du))
                else:
                    users_col.update_one({"email": du["email"]}, {"$set": {
                        "role": du["role"],
                        "assignedZoneId": du.get("assignedZoneId"),
                        "assignedZoneName": du.get("assignedZoneName")
                    }})
            print("✅ Synchronized default Admin and Supervisor users in MongoDB")
            
            zones_col = db_instance["zones"]
            if zones_col.count_documents({}) == 0:
                zones_col.insert_many(default_zones)
                print("✅ Seeded 3 default facility zones with supervisor & buzzer configs in MongoDB")
            else:
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

            cams_col = db_instance["cameras"]
            if cams_col.count_documents({}) == 0:
                cams_col.insert_many(default_cameras)
                print("✅ Seeded 4 default CCTV cameras in MongoDB")
        except Exception as e:
            print(f"⚠️ Seeding warning: {e}")
    else:
        # Seed in-memory
        for du in default_users:
            found_idx = next((i for i, u in enumerate(mem_users) if u["email"] == du["email"]), None)
            if found_idx is None:
                mem_users.append(dict(du))
            else:
                mem_users[found_idx]["role"] = du["role"]
                mem_users[found_idx]["assignedZoneId"] = du.get("assignedZoneId")
                mem_users[found_idx]["assignedZoneName"] = du.get("assignedZoneName")

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

        if len(mem_cameras) == 0:
            mem_cameras.extend(default_cameras)

        # Seed realistic default detections / violations with Worker and Location info
        default_detections = [
            {
                "_id": "det_seed_01",
                "workerTag": "WRK-042 (Operator: Mahesh S.)",
                "personId": "Worker #1",
                "zoneId": "zone_01",
                "zoneName": "Heavy Assembly Bay 01",
                "zoneCode": "BAY-01",
                "cameraId": "cam_01",
                "cameraName": "Bay 01 Primary HD Cam",
                "location": "Heavy Fabrication Deck, South Column #4",
                "sourceType": "CCTV RTSP",
                "missingPPE": ["helmet"],
                "detectedClasses": [{"name": "Vest", "confidence": 0.94}, {"name": "safety_shoe", "confidence": 0.89}],
                "complianceStatus": "VIOLATION",
                "reviewStatus": "PENDING",
                "reviewerNotes": "",
                "supervisorName": "Vikram Patil",
                "personCount": 1,
                "timestamp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=14),
                "createdAt": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=14)
            },
            {
                "_id": "det_seed_02",
                "workerTag": "WRK-108 (Helper: Ramesh G.)",
                "personId": "Worker #2",
                "zoneId": "zone_01",
                "zoneName": "Heavy Assembly Bay 01",
                "zoneCode": "BAY-01",
                "cameraId": "cam_01",
                "cameraName": "Bay 01 Primary HD Cam",
                "location": "Overhead Gantry Crane Loading Dock",
                "sourceType": "CCTV RTSP",
                "missingPPE": ["helmet", "vest"],
                "detectedClasses": [{"name": "safety_shoe", "confidence": 0.82}],
                "complianceStatus": "VIOLATION",
                "reviewStatus": "PENDING",
                "reviewerNotes": "",
                "supervisorName": "Vikram Patil",
                "personCount": 1,
                "timestamp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=38),
                "createdAt": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=38)
            },
            {
                "_id": "det_seed_03",
                "workerTag": "WRK-215 (Chemist: Pooja K.)",
                "personId": "Worker #1",
                "zoneId": "zone_02",
                "zoneName": "Chemical & Paint Processing",
                "zoneCode": "CHEM-02",
                "cameraId": "cam_02",
                "cameraName": "Chemical Line Cam 02",
                "location": "Solvents & Spray Booths, Vat Area",
                "sourceType": "IP Camera",
                "missingPPE": ["goggles", "mask"],
                "detectedClasses": [{"name": "helmet", "confidence": 0.96}, {"name": "Vest", "confidence": 0.91}],
                "complianceStatus": "VIOLATION",
                "reviewStatus": "PENDING",
                "reviewerNotes": "",
                "supervisorName": "Pooja Kulkarni",
                "personCount": 1,
                "timestamp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1, minutes=12),
                "createdAt": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1, minutes=12)
            },
            {
                "_id": "det_seed_04",
                "workerTag": "WRK-077 (Scaffolder: Sachin D.)",
                "personId": "Worker #3",
                "zoneId": "zone_03",
                "zoneName": "General Construction Deck",
                "zoneCode": "CONST-03",
                "cameraId": "cam_03",
                "cameraName": "Scaffold Deck Cam 03",
                "location": "Civil Engineering Deck, Level 2",
                "sourceType": "Webcam",
                "missingPPE": ["vest"],
                "detectedClasses": [{"name": "helmet", "confidence": 0.95}],
                "complianceStatus": "VIOLATION",
                "reviewStatus": "APPROVED",
                "reviewerNotes": "Worker issued new reflective jacket from emergency locker.",
                "supervisorName": "Sachin Deshmukh",
                "personCount": 1,
                "timestamp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2, minutes=5),
                "createdAt": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2, minutes=5)
            }
        ]

        if len(mem_detections) == 0:
            mem_detections.extend(default_detections)

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

def get_cameras_col():
    if is_mongo_connected and db_instance is not None:
        return db_instance["cameras"]
    return None

