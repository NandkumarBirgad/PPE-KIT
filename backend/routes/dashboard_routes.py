import datetime
from flask import Blueprint, jsonify
from database import is_mongo_connected, get_detections_col, get_zones_col, mem_detections, mem_zones

dashboard_bp = Blueprint("dashboard_bp", __name__)

@dashboard_bp.route("/api/dashboard/summary", methods=["GET"])
def get_summary():
    if is_mongo_connected:
        try:
            col = get_detections_col()
            total = col.count_documents({})
            compliant = col.count_documents({"complianceStatus": "COMPLIANT"})
            violations = col.count_documents({"complianceStatus": "VIOLATION"})
            uncertain = col.count_documents({"complianceStatus": "UNCERTAIN"})
            
            rate = round((compliant / total) * 100) if total > 0 else 100
            
            person_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$personCount"}}}]
            p_agg = list(col.aggregate(person_pipeline))
            monitored_persons = p_agg[0]["total"] if p_agg else total

            return jsonify({
                "totalEvents": total,
                "compliantEvents": compliant,
                "violationEvents": violations,
                "uncertainEvents": uncertain,
                "complianceRate": rate,
                "monitoredPersons": monitored_persons
            }), 200
        except Exception:
            pass

    # In-memory summary
    total = len(mem_detections)
    compliant = sum(1 for e in mem_detections if e.get("complianceStatus") == "COMPLIANT")
    violations = sum(1 for e in mem_detections if e.get("complianceStatus") == "VIOLATION")
    uncertain = sum(1 for e in mem_detections if e.get("complianceStatus") == "UNCERTAIN")
    rate = round((compliant / total) * 100) if total > 0 else 100
    monitored_persons = sum(e.get("personCount", 1) for e in mem_detections)

    return jsonify({
        "totalEvents": total,
        "compliantEvents": compliant,
        "violationEvents": violations,
        "uncertainEvents": uncertain,
        "complianceRate": rate,
        "monitoredPersons": monitored_persons
    }), 200

@dashboard_bp.route("/api/dashboard/trends", methods=["GET"])
def get_trends():
    seven_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)

    if is_mongo_connected:
        try:
            col = get_detections_col()
            pipeline = [
                {"$match": {"createdAt": {"$gte": seven_days_ago}}},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                        "compliant": {"$sum": {"$cond": [{"$eq": ["$complianceStatus", "COMPLIANT"]}, 1, 0]}},
                        "violation": {"$sum": {"$cond": [{"$eq": ["$complianceStatus", "VIOLATION"]}, 1, 0]}},
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            agg = list(col.aggregate(pipeline))
            trends = [{"date": a["_id"], "compliant": a["compliant"], "violation": a["violation"]} for a in agg]
            return jsonify({"trends": trends}), 200
        except Exception:
            pass

    # In-memory trends
    trends_map = {}
    for i in range(7):
        day_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=6 - i)).strftime("%Y-%m-%d")
        trends_map[day_str] = {"date": day_str, "compliant": 0, "violation": 0}

    for e in mem_detections:
        created = e.get("createdAt")
        if created:
            if isinstance(created, datetime.datetime):
                d_str = created.strftime("%Y-%m-%d")
            else:
                d_str = str(created)[:10]
            if d_str in trends_map:
                if e.get("complianceStatus") == "COMPLIANT":
                    trends_map[d_str]["compliant"] += 1
                elif e.get("complianceStatus") == "VIOLATION":
                    trends_map[d_str]["violation"] += 1

    return jsonify({"trends": list(trends_map.values())}), 200

@dashboard_bp.route("/api/dashboard/zone-summary", methods=["GET"])
def get_zone_summary():
    zones_list = []
    if is_mongo_connected:
        try:
            z_col = get_zones_col()
            d_col = get_detections_col()
            zones = list(z_col.find({"active": True}))

            res = []
            for z in zones:
                z_name = z["name"]
                comp = d_col.count_documents({"zoneName": z_name, "complianceStatus": "COMPLIANT"})
                viol = d_col.count_documents({"zoneName": z_name, "complianceStatus": "VIOLATION"})
                res.append({
                    "id": str(z["_id"]),
                    "name": z_name,
                    "code": z.get("code", "ZN"),
                    "compliant": comp,
                    "violations": viol
                })
            return jsonify({"zones": res}), 200
        except Exception:
            pass

    # In-memory
    res = []
    for z in mem_zones:
        z_name = z["name"]
        comp = sum(1 for d in mem_detections if d.get("zoneName") == z_name and d.get("complianceStatus") == "COMPLIANT")
        viol = sum(1 for d in mem_detections if d.get("zoneName") == z_name and d.get("complianceStatus") == "VIOLATION")
        res.append({
            "id": str(z.get("_id")),
            "name": z_name,
            "code": z.get("code", "ZN"),
            "compliant": comp,
            "violations": viol
        })

    return jsonify({"zones": res}), 200
