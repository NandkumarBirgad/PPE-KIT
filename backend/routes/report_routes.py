import io
import csv
import datetime
from flask import Blueprint, request, jsonify, Response
from database import is_mongo_connected, get_detections_col, get_zones_col, mem_detections, mem_zones

report_bp = Blueprint("report_bp", __name__)

@report_bp.route("/api/reports/summary", methods=["GET"])
def get_reports_summary():
    start_date = request.args.get("startDate")
    end_date = request.args.get("endDate")

    # In-memory and Mongo aggregation support
    filtered_events = list(mem_detections)
    if is_mongo_connected:
        try:
            col = get_detections_col()
            query = {}
            if start_date or end_date:
                query["createdAt"] = {}
                if start_date:
                    query["createdAt"]["$gte"] = datetime.datetime.fromisoformat(start_date)
                if end_date:
                    ed = datetime.datetime.fromisoformat(end_date)
                    query["createdAt"]["$lte"] = ed + datetime.timedelta(days=1)
            filtered_events = list(col.find(query))
        except Exception:
            pass

    total = len(filtered_events)
    compliant = sum(1 for e in filtered_events if e.get("complianceStatus") == "COMPLIANT")
    violations = sum(1 for e in filtered_events if e.get("complianceStatus") == "VIOLATION")
    uncertain = sum(1 for e in filtered_events if e.get("complianceStatus") == "UNCERTAIN")
    rate = round((compliant / total) * 100) if total > 0 else 100

    # Violations by missing PPE
    ppe_counter = {}
    for e in filtered_events:
        if e.get("complianceStatus") == "VIOLATION":
            for item in e.get("missingPPE", []):
                item_name = item.capitalize()
                ppe_counter[item_name] = ppe_counter.get(item_name, 0) + 1

    by_ppe = [{"name": k, "count": v} for k, v in sorted(ppe_counter.items(), key=lambda x: x[1], reverse=True)]

    # Zone comparisons
    zone_stats = {}
    for e in filtered_events:
        z_name = e.get("zoneName", "General")
        if z_name not in zone_stats:
            zone_stats[z_name] = {"compliant": 0, "violations": 0}
        if e.get("complianceStatus") == "COMPLIANT":
            zone_stats[z_name]["compliant"] += 1
        elif e.get("complianceStatus") == "VIOLATION":
            zone_stats[z_name]["violations"] += 1

    by_zone = [{"name": k, "compliant": v["compliant"], "violations": v["violations"]} for k, v in zone_stats.items()]

    return jsonify({
        "summary": {
            "total": total,
            "compliant": compliant,
            "violations": violations,
            "uncertain": uncertain,
            "complianceRate": rate
        },
        "byPPE": by_ppe,
        "byZone": by_zone
    }), 200

@report_bp.route("/api/reports/export", methods=["GET"])
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Incident ID", "Timestamp", "Zone", "Source", "Compliance Status", "Missing PPE", "Review Status", "Reviewer Notes"
    ])

    events = list(mem_detections)
    if is_mongo_connected:
        try:
            col = get_detections_col()
            events = list(col.find().sort("createdAt", -1))
        except Exception:
            pass

    for ev in events:
        eid = str(ev.get("_id", ""))
        ts = str(ev.get("timestamp", ev.get("createdAt", "")))
        zn = ev.get("zoneName", "General")
        src = ev.get("sourceType", "webcam")
        st = ev.get("complianceStatus", "")
        mis = "; ".join(ev.get("missingPPE", []))
        rev = ev.get("reviewStatus", "PENDING")
        notes = ev.get("reviewerNotes", "")
        writer.writerow([eid, ts, zn, src, st, mis, rev, notes])

    csv_data = output.getvalue()
    today_str = datetime.date.today().isoformat()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ppe_compliance_audit_{today_str}.csv"}
    )
