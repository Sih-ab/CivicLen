
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
    send_from_directory
)


from road_matching import match_report_to_road, load_roads, projector
import os

import secrets
import hashlib
from datetime import datetime, timedelta

import pyodbc

import math

import json
from shapely.geometry import shape, Point

import uuid
from werkzeug.utils import secure_filename

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from flask import make_response, send_from_directory


app = Flask(__name__)

# Photo upload configuration
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE



# Session security
secret_key = os.environ.get("FLASK_SECRET_KEY")

if not secret_key and os.environ.get("APP_ENV") == "production":
    raise RuntimeError("FLASK_SECRET_KEY must be configured.")

app.config["SECRET_KEY"] = (
    secret_key or "dev-only-change-this-secret-key"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("APP_ENV") == "production"
)

# SQL Server connection settings

AZURE_SQL_CONNECTION_STRING = os.environ.get(
    "AZURE_SQL_CONNECTION_STRING"
)

LOCAL_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=SIHAB\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

if os.environ.get("APP_ENV") == "production":
    if not AZURE_SQL_CONNECTION_STRING:
        raise RuntimeError(
            "AZURE_SQL_CONNECTION_STRING must be configured."
        )
    CONNECTION_STRING = AZURE_SQL_CONNECTION_STRING
else:
    CONNECTION_STRING = (
        AZURE_SQL_CONNECTION_STRING or LOCAL_CONNECTION_STRING
    )

def get_connection():
    return pyodbc.connect(CONNECTION_STRING)


def update_road_risk_score(cursor, road_id):

    cursor.execute("""
        SELECT
            COUNT(*) AS TotalReports,

            COALESCE(SUM(
                CASE IssueType
                    WHEN 'Damaged Road' THEN 5
                    WHEN 'Pothole' THEN 4
                    WHEN 'Broken Drain' THEN 3
                    WHEN 'Waterlogging' THEN 3
                    WHEN 'Broken Streetlight' THEN 2
                    WHEN 'Other' THEN 1
                    ELSE 0
                END
            ), 0) AS RawRiskPoints

        FROM dbo.Reports

        WHERE RoadID = ?
          AND Status IN ('Pending', 'In Progress')
    """, (road_id,))

    result = cursor.fetchone()

    total_reports = result.TotalReports
    raw_points = result.RawRiskPoints

    risk_score = min(raw_points * 10, 100)

    if risk_score >= 70:
        risk_level = "High"
    elif risk_score >= 40:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    cursor.execute("""
        SELECT RoadID
        FROM dbo.RoadRiskScores
        WHERE RoadID = ?
    """, (road_id,))

    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE dbo.RoadRiskScores
            SET
                TotalReports = ?,
                RawRiskPoints = ?,
                RiskScore = ?,
                RiskLevel = ?,
                LastCalculatedAt = SYSUTCDATETIME()
            WHERE RoadID = ?
        """, (
            total_reports,
            raw_points,
            risk_score,
            risk_level,
            road_id
        ))

    else:
        cursor.execute("""
            INSERT INTO dbo.RoadRiskScores
                (RoadID, TotalReports, RawRiskPoints,
                 RiskScore, RiskLevel, LastCalculatedAt)
            VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
        """, (
            road_id,
            total_reports,
            raw_points,
            risk_score,
            risk_level
        ))








# ----------------------------------
# Ward Detection
# ----------------------------------

def get_ward_number(latitude, longitude):

    geojson_path = os.path.join(
        app.root_path,
        "rcc_wards.geojson"
    )

    with open(geojson_path, "r", encoding="utf-8") as file:
        geojson_data = json.load(file)

    point = Point(float(longitude), float(latitude))

    matched_wards = []

    for feature in geojson_data["features"]:
        ward_number = feature["properties"].get("ward_name")
        polygon = shape(feature["geometry"])

        if polygon.covers(point):
            matched_wards.append(str(ward_number))

    if len(matched_wards) == 1:
        return matched_wards[0]

    return None

def haversine_distance_m(lat1, lon1, lat2, lon2):
    earth_radius = 6371000

    lat1, lon1, lat2, lon2 = map(
        math.radians, [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius * c



# ----------------------------------
# Dashboard
# ----------------------------------

@app.route("/google3e77425aeb8e7f63.html")
def google_site_verification():
    return send_from_directory(
        app.root_path,
        "google3e77425aeb8e7f63.html"
    )


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    response = make_response(
        render_template(
            "index.html",
            user_name=session.get("user_name", "Citizen")
        )
    )

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response



@app.route("/authority")
def authority_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("user_role") != "Authority":
        return redirect(url_for("home"))

    return render_template(
        "authority.html",
        user_name=session.get("user_name", "Authority")
    )


@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("user_role") != "Admin":
        return redirect(url_for("home"))

    response = make_response(
        render_template(
            "admin.html",
            user_name=session.get("user_name", "Admin")
        )
    )

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response




# ----------------------------------
# Login page
# ----------------------------------

@app.route("/login")
def login_page():
    return render_template("login.html")

# ----------------------------------
# Forgot Password page
# ----------------------------------

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ----------------------------------
# Registration page
# ----------------------------------

@app.route("/register")
def register_page():
    return render_template("register.html")


# ----------------------------------
# Registration API
# ----------------------------------

@app.route("/api/register", methods=["POST"])
def register_user():

    data = request.get_json(silent=True) or {}

    full_name = data.get("full_name", "")
    email = data.get("email", "")
    password = data.get("password", "")

    if not all(isinstance(value, str) for value in
               (full_name, email, password)):
        return jsonify({
            "success": False,
            "error": "Invalid input."
        }), 400

    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or not email or not password:
        return jsonify({
            "success": False,
            "error": "Please fill in all required fields."
        }), 400

    if len(full_name) > 100 or len(email) > 254:
        return jsonify({
            "success": False,
            "error": "Name or email is too long."
        }), 400

    if len(password) < 8:
        return jsonify({
            "success": False,
            "error": "Password must contain at least 8 characters."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT UserID FROM dbo.Users WHERE Email = ?",
            (email,)
        )

        if cursor.fetchone():
            return jsonify({
                "success": False,
                "error": "An account with this email already exists."
            }), 409

        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO dbo.Users
                (FullName, Email, PasswordHash, Role)
            VALUES (?, ?, ?, ?)
        """, (
            full_name,
            email,
            password_hash,
            "Citizen"
        ))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Account created successfully."
        }), 201

    except Exception:
        app.logger.exception("Registration failed")

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Registration failed. Please try again."
        }), 500

    finally:
        if connection is not None:
            connection.close()



@app.route("/api/admin/authorities", methods=["POST"])
def create_authority_user():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    if session.get("user_role") != "Admin":
        return jsonify({
            "success": False,
            "error": "Only an Admin can create an Authority account."
        }), 403

    data = request.get_json(silent=True) or {}

    full_name = data.get("full_name", "")
    email = data.get("email", "")
    password = data.get("password", "")

    if not all(
        isinstance(value, str)
        for value in (full_name, email, password)
    ):
        return jsonify({
            "success": False,
            "error": "Invalid input."
        }), 400

    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or not email or not password:
        return jsonify({
            "success": False,
            "error": "Name, email, and password are required."
        }), 400

    if len(full_name) > 100 or len(email) > 254:
        return jsonify({
            "success": False,
            "error": "Name or email is too long."
        }), 400

    if len(password) < 8:
        return jsonify({
            "success": False,
            "error": "Password must contain at least 8 characters."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT UserID
            FROM dbo.Users
            WHERE Email = ?
        """, (email,))

        if cursor.fetchone():
            return jsonify({
                "success": False,
                "error": "An account with this email already exists."
            }), 409

        cursor.execute("""
            INSERT INTO dbo.Users
                (FullName, Email, PasswordHash, Role)
            OUTPUT INSERTED.UserID
            VALUES (?, ?, ?, ?)
        """, (
            full_name,
            email,
            generate_password_hash(password),
            "Authority"
        ))

        user_id = cursor.fetchone()[0]
        connection.commit()

        return jsonify({
            "success": True,
            "message": "Authority account created successfully.",
            "user_id": user_id
        }), 201

    except Exception:
        app.logger.exception("Authority account creation failed")

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Could not create the Authority account."
        }), 500

    finally:
        if connection is not None:
            connection.close()



# ----------------------------------
# Login API
# ----------------------------------

@app.route("/api/login", methods=["POST"])
def login_user():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "")
    password = data.get("password", "")

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({
            "success": False,
            "error": "Invalid input."
        }), 400

    email = email.strip().lower()

    if not email or not password:
        return jsonify({
            "success": False,
            "error": "Please enter your email and password."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT UserID, FullName, Email, PasswordHash, Role
            FROM dbo.Users
            WHERE Email = ?
        """, (email,))

        user = cursor.fetchone()

        if (
            user is None
            or not user[3]
            or not check_password_hash(user[3], password)
        ):
            return jsonify({
                "success": False,
                "error": "Invalid email or password."
            }), 401

        # Create a fresh session after successful authentication.
        session.clear()
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        session["user_role"] = user[4]

       
        if user[4] == "Authority":
            redirect_url = url_for("authority_dashboard")
        elif user[4] == "Admin":
            redirect_url = url_for("admin_dashboard")
        else:
            redirect_url = url_for("home")

        return jsonify({
            "success": True,
            "redirect": redirect_url
        })



    except Exception:
        app.logger.exception("Login failed")

        return jsonify({
            "success": False,
            "error": "Login failed because of a server error."
        }), 500

    finally:
        if connection is not None:
            connection.close()


# ----------------------------------
# Forgot Password API
# ----------------------------------

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "")

    if not isinstance(email, str):
        return jsonify({
            "success": False,
            "message": "Invalid email address."
        }), 400

    email = email.strip().lower()

    if not email:
        return jsonify({
            "success": False,
            "message": "Please enter your email address."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Find registered user
        cursor.execute("""
            SELECT UserID
            FROM dbo.Users
            WHERE Email = ?
        """, (email,))

        user = cursor.fetchone()

        if user is None:
            return jsonify({
                "success": False,
                "message": "No account found with this email."
            }), 404

        user_id = user[0]

        # Generate secure random token
        reset_token = secrets.token_urlsafe(32)

        # Store only the token hash
        token_hash = hashlib.sha256(
            reset_token.encode("utf-8")
        ).hexdigest()

        # Token expires after 15 minutes
        expires_at = datetime.now() + timedelta(minutes=15)

        # Remove previous unused reset tokens
        cursor.execute("""
            DELETE FROM dbo.PasswordResetTokens
            WHERE UserID = ?
              AND UsedAt IS NULL
        """, (user_id,))

        # Save new reset token
        cursor.execute("""
            INSERT INTO dbo.PasswordResetTokens
                (UserID, TokenHash, ExpiresAt)
            VALUES (?, ?, ?)
        """, (
            user_id,
            token_hash,
            expires_at
        ))

        connection.commit()

        # Demo reset link (no email is sent)
        reset_link = (
            request.host_url.rstrip("/")
            + "/reset-password/"
            + reset_token
        )

        return jsonify({
            "success": True,
            "message": "Reset link generated successfully.",
            "reset_link": reset_link
        }), 200

    except Exception:
        app.logger.exception("Forgot password failed")

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "message": "Could not process your request."
        }), 500

    finally:
        if connection is not None:
            connection.close()


# ----------------------------------
# Reset Password Page
# ----------------------------------

@app.route("/reset-password/<token>")
def reset_password_page(token):
    return render_template(
        "reset_password.html",
        token=token
    )


# ----------------------------------
# Reset Password API
# ----------------------------------

@app.route("/api/reset-password", methods=["POST"])
def reset_password():

    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    new_password = data.get("password", "")

    if not isinstance(token, str) or not isinstance(new_password, str):
        return jsonify({
            "success": False,
            "message": "Invalid request."
        }), 400

    if not token or not new_password:
        return jsonify({
            "success": False,
            "message": "Please provide all required information."
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "success": False,
            "message": "Password must contain at least 8 characters."
        }), 400

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Validate token and lock it during password reset
        cursor.execute("""
            SELECT UserID
            FROM dbo.PasswordResetTokens
                WITH (UPDLOCK, ROWLOCK)
            WHERE TokenHash = ?
              AND UsedAt IS NULL
              AND ExpiresAt > GETDATE()
        """, (token_hash,))

        reset_record = cursor.fetchone()

        if reset_record is None:
            return jsonify({
                "success": False,
                "message": "This reset link is invalid or has expired."
            }), 400

        user_id = reset_record[0]

        # Hash the new password
        new_password_hash = generate_password_hash(new_password)

        # Update user password
        cursor.execute("""
            UPDATE dbo.Users
            SET PasswordHash = ?
            WHERE UserID = ?
        """, (
            new_password_hash,
            user_id
        ))

        # Mark all reset tokens for this user as used
        cursor.execute("""
            UPDATE dbo.PasswordResetTokens
            SET UsedAt = GETDATE()
            WHERE UserID = ?
              AND UsedAt IS NULL
        """, (user_id,))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Password updated successfully. You can now sign in."
        }), 200

    except Exception:
        app.logger.exception("Password reset failed")

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "message": "Could not reset your password. Please try again."
        }), 500

    finally:
        if connection is not None:
            connection.close()











# ----------------------------------
# Roads API
# ----------------------------------

@app.route("/api/reports", methods=["POST"])
def create_report():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    issue_type = request.form.get("issue_type", "")
    description = request.form.get("description", "").strip()
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    photo = request.files.get("photo")

    allowed_issue_types = {
        "Pothole",
        "Damaged Road",
        "Waterlogging",
        "Broken Drain",
        "Broken Streetlight",
        "Other"
    }

    if issue_type not in allowed_issue_types:
        return jsonify({
            "success": False,
            "error": "Please select a valid issue type."
        }), 400

    if not description:
        return jsonify({
            "success": False,
            "error": "Please describe the road issue."
        }), 400

    if len(description) > 2000:
        return jsonify({
            "success": False,
            "error": "Description must be 2000 characters or fewer."
        }), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90):
            raise ValueError()

        if not (-180 <= longitude <= 180):
            raise ValueError()

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Please select a valid location on the map."
        }), 400

    if photo and photo.filename:
        if not allowed_file(photo.filename):
            return jsonify({
                "success": False,
                "error": "Only PNG, JPG, JPEG, and WEBP images are allowed."
            }), 400

        photo_data = photo.read()

        if not photo_data:
            return jsonify({
                "success": False,
                "error": "The selected image is empty."
            }), 400

        if len(photo_data) > MAX_IMAGE_SIZE:
            return jsonify({
                "success": False,
                "error": "Image size must be 5 MB or less."
            }), 400

        photo.seek(0)
    else:
        photo_data = None



    # Detect Ward from report location
    ward_number = get_ward_number(latitude, longitude)

    if ward_number is None:
       return jsonify({
           "success": False,
           "error": "Selected location is outside the available ward boundaries."
       }), 400  




    connection = None
    saved_photo_path = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
               
        # Automatically match report location to a road
        road_id = None
        match_confidence = None
        match_reason = None
        match_distance = None
        match_distance_gap = None
        match_candidates = None
        road_review_status = "NoMatch"

        try:
            match_result = match_report_to_road(latitude, longitude)

            match_confidence = match_result.get("confidence")
            match_reason = match_result.get("reason")

            if match_result.get("candidates"):
                match_candidates = json.dumps(
                    match_result["candidates"],
                    ensure_ascii=False,
                    default=str
                )

            if match_result.get("candidates"):
                match_distance = match_result["candidates"][0].get(
                    "DistanceMeters"
                )

            match_distance_gap = match_result.get("distance_gap")

            if match_result.get("matched") and match_result.get("road"):
                matched_osmid = match_result["road"]["OSMID"]

                cursor.execute("""
                    SELECT RoadID
                    FROM dbo.Roads
                    WHERE OSMID = ?
                """, (matched_osmid,))

                matched_road = cursor.fetchone()

                if matched_road:
                    road_id = matched_road[0]
                    road_review_status = "AutoMatched"
                else:
                    road_review_status = "PendingReview"

            elif match_confidence == "Moderate":
                road_review_status = "PendingReview"

            else:
                road_review_status = "NoMatch"

        except Exception:
            app.logger.exception("Automatic road matching failed")
            road_review_status = "NoMatch"



        

            # Duplicate Report Detection
        confirm_duplicate = request.form.get("confirm_duplicate") == "true"

        cursor.execute("""
            SELECT Latitude, Longitude
            FROM dbo.Reports
            WHERE IssueType = ?
              AND WardNumber = ?
              AND ReportedAt >= DATEADD(day, -7, SYSUTCDATETIME())
              AND Latitude IS NOT NULL
              AND Longitude IS NOT NULL
        """, (issue_type, ward_number))

        recent_reports = cursor.fetchall()

        nearby_duplicates = []

        for report in recent_reports:
            distance = haversine_distance_m(
                latitude,
                longitude,
                float(report.Latitude),
                float(report.Longitude)
            )

            if distance <= 50:
                nearby_duplicates.append(distance)

        if nearby_duplicates and not confirm_duplicate:
            return jsonify({
                "success": False,
                "possible_duplicate": True,
                "error": "A similar report was found within 50 meters in the last 7 days.",
                "duplicate_count": len(nearby_duplicates),
                "nearest_distance_m": round(min(nearby_duplicates), 1)
            }), 409

        cursor.execute("""
            INSERT INTO dbo.Reports
                (
                    UserID,
                    RoadID,
                    IssueType,
                    Description,
                    Latitude,
                    Longitude,
                    Status,
                    ReportedAt,
                    WardNumber,
                    RoadMatchConfidence,
                    RoadMatchReason,
                    RoadMatchDistanceMeters,
                    RoadMatchDistanceGapMeters,
                    RoadMatchCandidates,
                    RoadReviewStatus
                )
            OUTPUT INSERTED.ReportID
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                SYSUTCDATETIME(),
                ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            session["user_id"],
            road_id,
            issue_type,
            description,
            latitude,
            longitude,
            "Pending",
            ward_number,
            match_confidence,
            match_reason,
            match_distance,
            match_distance_gap,
            match_candidates,
            road_review_status
        ))

        report_id = cursor.fetchone()[0]

    

        # Automatically assign the new report to Rajshahi City Corporation
        cursor.execute("""
            SELECT TOP 1 AuthorityID
            FROM dbo.Authorities
            WHERE AuthorityName = ?
              AND City = ?
              AND IsActive = 1
            ORDER BY AuthorityID
        """, (
            "Rajshahi City Corporation",
            "Rajshahi"
        ))

        authority = cursor.fetchone()

        if authority is None:
            raise Exception(
                "Active Rajshahi City Corporation authority not found."
            )

        authority_id = authority[0]

        cursor.execute("""
            INSERT INTO dbo.ReportAssignments
                (ReportID, AuthorityID, AssignmentStatus, Remarks)
            VALUES (?, ?, ?, ?)
        """, (
            report_id,
            authority_id,
            "Assigned",
            "Automatically assigned when the citizen submitted the report."
        ))


        cursor.execute("""
            INSERT INTO dbo.ReportStatusHistory
                (ReportID, PreviousStatus, NewStatus, ChangedBy, Remarks, ChangedAt)
            VALUES (?, NULL, ?, NULL, ?, SYSUTCDATETIME())
        """, (
            report_id,
            "Pending",
            "Report submitted"
        ))

       



        if photo_data is not None:
            original_filename = secure_filename(photo.filename)

            extension = original_filename.rsplit(".", 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{extension}"

            saved_photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                unique_filename
            )

            photo.save(saved_photo_path)

            relative_path = f"uploads/{unique_filename}"

            cursor.execute("""
                INSERT INTO dbo.ReportImages
                    (ReportID, FilePath, OriginalFileName, UploadedAt)
                VALUES (?, ?, ?, SYSUTCDATETIME())
            """, (
                report_id,
                relative_path,
                original_filename
            ))


            # Automatically update road risk score
        if road_id is not None:
            update_road_risk_score(cursor, road_id)



        connection.commit()

        return jsonify({
            "success": True,
            "message": "Report submitted successfully.",
            "report_id": report_id
        }), 201

    except Exception:
        app.logger.exception("Report submission failed")

        if connection is not None:
            connection.rollback()

        if saved_photo_path and os.path.exists(saved_photo_path):
            os.remove(saved_photo_path)

        return jsonify({
            "success": False,
            "error": "Could not save the report. Please try again."
        }), 500

    finally:
        if connection is not None:
            connection.close()

# ----------------------------------------
# Reports API
# ----------------------------------------
@app.route("/api/report-trends", methods=["GET"])
def get_report_trends():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                YEAR(ReportedAt) AS ReportYear,
                MONTH(ReportedAt) AS ReportMonth,
                COUNT(*) AS ReportCount
            FROM dbo.Reports
            WHERE ReportedAt >= DATEADD(
                MONTH,
                -5,
                DATEFROMPARTS(
                    YEAR(GETDATE()),
                    MONTH(GETDATE()),
                    1
                )
            )
            AND ReportedAt < DATEADD(
                MONTH,
                1,
                DATEFROMPARTS(
                    YEAR(GETDATE()),
                    MONTH(GETDATE()),
                    1
                )
            )
            GROUP BY
                YEAR(ReportedAt),
                MONTH(ReportedAt)
            ORDER BY
                ReportYear,
                ReportMonth
        """)

        rows = cursor.fetchall()

        monthly_reports = {}

        for row in rows:
            key = (row.ReportYear, row.ReportMonth)
            monthly_reports[key] = row.ReportCount

        from datetime import datetime

        current_date = datetime.utcnow()

        months = []

        for i in range(5, -1, -1):

            month_index = current_date.month - 1 - i
            year = current_date.year + month_index // 12
            month = month_index % 12 + 1

            count = monthly_reports.get((year, month), 0)

            months.append({
                "year": year,
                "month": month,
                "report_count": count
            })

        total_reports = sum(
            item["report_count"] for item in months
        )

        return jsonify({
            "success": True,
            "months": months,
            "total_reports": total_reports
        })

    except Exception:
        app.logger.exception("Report trends API failed")

        return jsonify({
            "success": False,
            "error": "Could not load report trends."
        }), 500

    finally:
        if connection is not None:
            connection.close()

            

@app.route("/api/reports", methods=["GET"])
def get_reports():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]
    user_role = session.get("user_role")

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        if user_role == "Admin":
            cursor.execute("""
                SELECT
                    r.ReportID,
                    r.RoadID,
                    r.IssueType,
                    r.Description,
                    r.Latitude,
                    r.Longitude,
                    r.WardNumber,
                    r.Status,
                    r.ReportedAt,
                    a.AuthorityName,
                    ra.AssignmentStatus,
                    r.RoadMatchConfidence,
                    r.RoadMatchReason,
                    r.RoadMatchDistanceMeters,
                    r.RoadMatchDistanceGapMeters,
                    r.RoadMatchCandidates,
                    r.RoadReviewStatus
                FROM dbo.Reports r
                LEFT JOIN dbo.ReportAssignments ra
                    ON r.ReportID = ra.ReportID
                LEFT JOIN dbo.Authorities a
                    ON ra.AuthorityID = a.AuthorityID
                ORDER BY r.ReportedAt DESC
            """)

        elif user_role == "Authority":
            cursor.execute("""
                SELECT
    r.ReportID,
    r.RoadID,
    r.IssueType,
    r.Description,
    r.Latitude,
    r.WardNumber,
    r.Longitude,
    r.Status,
    r.ReportedAt,
        assignment.AuthorityName,
    assignment.AssignmentStatus,
    r.RoadMatchConfidence,
    r.RoadMatchReason,
    r.RoadMatchDistanceMeters,
    r.RoadMatchDistanceGapMeters,
    r.RoadMatchCandidates,
    r.RoadReviewStatus

FROM dbo.Reports r

CROSS APPLY (
    SELECT TOP 1
        a.AuthorityName,
        ra.AssignmentStatus

    FROM dbo.ReportAssignments ra

    INNER JOIN dbo.Authorities a
        ON ra.AuthorityID = a.AuthorityID

    WHERE ra.ReportID = r.ReportID
      AND a.AuthorityName = ?
      AND a.IsActive = 1

    ORDER BY a.AuthorityID ASC

) AS assignment

ORDER BY r.ReportedAt DESC
            """, ("Rajshahi City Corporation",))

        else:
            cursor.execute("""
                SELECT
                    r.ReportID,
                    r.RoadID,
                    r.IssueType,
                    r.Description,
                    r.Latitude,
                    r.WardNumber,
                    r.Longitude,
                    r.Status,
                    r.ReportedAt,
                    CAST(NULL AS NVARCHAR(200)) AS AuthorityName,
                    CAST(NULL AS NVARCHAR(30)) AS AssignmentStatus,
                    rf.FeedbackStatus,
                    rr.RequestStatus AS ReopenRequestStatus
                FROM dbo.Reports r
                LEFT JOIN dbo.ReportFeedback rf
                    ON rf.ReportID = r.ReportID
                    AND rf.UserID = r.UserID
                OUTER APPLY (
                    SELECT TOP 1 RequestStatus
                    FROM dbo.ReportReopenRequests
                    WHERE ReportID = r.ReportID
                      AND UserID = r.UserID
                    ORDER BY RequestedAt DESC, RequestID DESC
                ) rr
                WHERE r.UserID = ?
                ORDER BY r.ReportedAt DESC
            """, (user_id,))



        print("ACTIVE ROLE:", user_role)
        print("SQL QUERY COLUMNS:", [column[0] for column in cursor.description])
        reports = []

        for row in cursor.fetchall():
            reports.append({
                "report_id": row.ReportID,
                "road_id": row.RoadID,
                "issue_type": row.IssueType,
                "description": row.Description,
                "latitude": (
                    float(row.Latitude)
                    if row.Latitude is not None else None
                ),
               "longitude": (
    float(row.Longitude)
    if row.Longitude is not None else None
),
"ward_number": row.WardNumber,
"status": row.Status,
                "reported_at": (
                    row.ReportedAt.isoformat()
                    if row.ReportedAt else None
                ),
                "authority_name": row.AuthorityName,
                               "assignment_status": row.AssignmentStatus,

                "road_match_confidence": (
                    getattr(row, "RoadMatchConfidence", None)
                    if user_role in {"Admin", "Authority"}
                    else None
                ),

                "road_match_reason": (
                    getattr(row, "RoadMatchReason", None)
                    if user_role in {"Admin", "Authority"}
                    else None
                ),

                "road_match_distance_meters": (
                    float(row.RoadMatchDistanceMeters)
                    if user_role in {"Admin", "Authority"}
                    and row.RoadMatchDistanceMeters is not None
                    else None
                ),

                "road_match_distance_gap_meters": (
                    float(row.RoadMatchDistanceGapMeters)
                    if user_role in {"Admin", "Authority"}
                    and row.RoadMatchDistanceGapMeters is not None
                    else None
                ),

                "road_match_candidates": (
                    getattr(row, "RoadMatchCandidates", None)
                    if user_role in {"Admin", "Authority"}
                    else None
                ),

                "road_review_status": (
                    getattr(row, "RoadReviewStatus", None)
                    if user_role in {"Admin", "Authority"}
                    else None
                ),

                "feedback_status": getattr(row, "FeedbackStatus", None),

                "reopen_request_status": getattr(
                    row, "ReopenRequestStatus", None
                )
            })


        print("FIRST REPORT JSON:", reports[0] if reports else "NO REPORTS")

        return jsonify({
            "success": True,
            "total": len(reports),
            "reports": reports
        })

    except Exception as e:
        app.logger.exception("Failed to fetch reports: %s", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if connection is not None:
            connection.close()


@app.route("/api/reports/<int:report_id>/images", methods=["GET"])
def get_report_images(report_id):
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        user_id = session["user_id"]

        # Use the same session key as the status API.
        user_role = session.get("user_role", "")

        cursor.execute("""
            SELECT
                ri.ImageID,
                ri.FilePath,
                ri.OriginalFileName
            FROM dbo.ReportImages AS ri
            INNER JOIN dbo.Reports AS r
                ON ri.ReportID = r.ReportID
            WHERE ri.ReportID = ?
              AND (
                    r.UserID = ?
                    OR ? = 'Admin'
                    OR (
                        ? = 'Authority'
                        AND EXISTS (
                            SELECT 1
                            FROM dbo.ReportAssignments AS ra
                            INNER JOIN dbo.Authorities AS a
                                ON ra.AuthorityID = a.AuthorityID
                            WHERE ra.ReportID = r.ReportID
                              AND ra.AssignmentStatus = 'Assigned'
                              AND a.AuthorityName =
                                  'Rajshahi City Corporation'
                        )
                    )
              )
            ORDER BY ri.ImageID DESC
        """, (
            report_id,
            user_id,
            user_role,
            user_role
        ))

        rows = cursor.fetchall()
        images = []

        for row in rows:
            images.append({
                "image_id": row.ImageID,
                "url": url_for(
                    "static",
                    filename=row.FilePath.replace("\\", "/")
                ),
                "original_filename": row.OriginalFileName
            })

        return jsonify({
            "success": True,
            "images": images
        }), 200

    except Exception:
        app.logger.exception(
            "Failed to fetch report images for report ID %s",
            report_id
        )

        return jsonify({
            "success": False,
            "error": "Could not load report images."
        }), 500

    finally:
        if connection is not None:
            connection.close()





@app.route("/api/reports/<int:report_id>/status", methods=["POST"])
def update_report_status(report_id):
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]
    user_role = session.get("user_role", "")

    if user_role not in {"Admin", "Authority"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized to update report status."
        }), 403

    data = request.get_json(silent=True) or {}

    new_status = data.get("status")
    remarks = data.get("remarks", "")

    allowed_statuses = {
        "Pending",
        "In Progress",
        "Resolved"
    }

    if new_status not in allowed_statuses:
        return jsonify({
            "success": False,
            "error": "Invalid report status."
        }), 400

    if not isinstance(remarks, str):
        return jsonify({
            "success": False,
            "error": "Remarks must be text."
        }), 400

    remarks = remarks.strip()

    if len(remarks) > 1000:
        return jsonify({
            "success": False,
            "error": "Remarks must be 1000 characters or fewer."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Verify that the report exists and the user is authorized.
        cursor.execute("""
            SELECT r.Status, r.UserID, r.RoadID
FROM dbo.Reports AS r
WHERE r.ReportID = ?
              AND (
                    ? = 'Admin'
                    OR (
                        ? = 'Authority'
                        AND EXISTS (
                            SELECT 1
                            FROM dbo.ReportAssignments AS ra
                            INNER JOIN dbo.Authorities AS a
                                ON ra.AuthorityID = a.AuthorityID
                            WHERE ra.ReportID = r.ReportID
                              AND ra.AssignmentStatus = 'Assigned'
                              AND a.AuthorityName =
                                  'Rajshahi City Corporation'
                        )
                    )
              )
        """, (
            report_id,
            user_role,
            user_role
        ))

        row = cursor.fetchone()

        if row is None:
            # Do not disclose whether an unauthorized report exists.
            return jsonify({
                "success": False,
                "error": "Report not found or you are not authorized to update it."
            }), 404

        previous_status = row.Status
        citizen_user_id = row.UserID
        road_id = row.RoadID

        if previous_status == new_status:
            return jsonify({
                "success": True,
                "message": "Report already has this status."
            }), 200

        cursor.execute("""
            UPDATE dbo.Reports
            SET Status = ?
            WHERE ReportID = ?
        """, (
            new_status,
            report_id
        ))

        cursor.execute("""
            INSERT INTO dbo.ReportStatusHistory
                (
                    ReportID,
                    PreviousStatus,
                    NewStatus,
                    ChangedBy,
                    Remarks,
                    ChangedAt
                )
            VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
        """, (
            report_id,
            previous_status,
            new_status,
            user_id,
            remarks or None
        ))


            # Create a notification for the citizen

        if new_status == "In Progress":
            notification_title = "Your Report Is Being Reviewed"
            notification_message = (
                f"Your report #{report_id} is now being reviewed "
                "by the responsible authority."
            )

        elif new_status == "Resolved":
            notification_title = "Your Report Has Been Resolved"
            notification_message = (
                f"Good news! Your report #{report_id} "
                "has been marked as resolved."
            )

        else:
            notification_title = "Your Report Status Has Changed"
            notification_message = (
                f"Your report #{report_id} status has been "
                f"updated to {new_status}."
            )

        cursor.execute("""
            INSERT INTO dbo.Notifications
                (UserID, ReportID, Title, Message)
            VALUES (?, ?, ?, ?)
        """, (
            citizen_user_id,
            report_id,
            notification_title,
            notification_message
        ))

                # Automatically recalculate road risk score
        if road_id is not None:
            update_road_risk_score(cursor, road_id)

            app.logger.info(
                "Risk score recalculated for RoadID: %s",
                road_id
            )

        connection.commit()
           
        return jsonify({
            "success": True,
            "message": "Report status updated successfully.",
            "report_id": report_id,
            "previous_status": previous_status,
            "new_status": new_status
        }), 200

    except Exception:
        app.logger.exception(
            "Report status update failed for report ID %s",
            report_id
        )

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Could not update report status."
        }), 500

    finally:
        if connection is not None:
            connection.close()



@app.route("/api/notifications", methods=["GET"])
def get_notifications():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                NotificationID,
                ReportID,
                Title,
                Message,
                IsRead,
                CreatedAt
            FROM dbo.Notifications
            WHERE UserID = ?
            ORDER BY CreatedAt DESC
        """, (user_id,))

        rows = cursor.fetchall()

        notifications = []

        for row in rows:
            notifications.append({
                "notification_id": row.NotificationID,
                "report_id": row.ReportID,
                "title": row.Title,
                "message": row.Message,
                "is_read": bool(row.IsRead),
                "created_at": row.CreatedAt.isoformat()
            })

        return jsonify({
            "success": True,
            "notifications": notifications,
            "unread_count": sum(
                1 for n in notifications if not n["is_read"]
            )
        }), 200

    except Exception:
        app.logger.exception("Failed to fetch notifications.")

        return jsonify({
            "success": False,
            "error": "Could not load notifications."
        }), 500

    finally:
        if connection is not None:
            connection.close()


@app.route(
    "/api/notifications/<int:notification_id>/read",
    methods=["POST"]
)
def mark_notification_read(notification_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE dbo.Notifications
            SET IsRead = 1
            WHERE NotificationID = ?
              AND UserID = ?
        """, (notification_id, user_id))

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "error": "Notification not found."
            }), 404

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Notification marked as read."
        }), 200

    except Exception:
        app.logger.exception("Failed to mark notification as read.")

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Could not update notification."
        }), 500

    finally:
        if connection is not None:
            connection.close()




@app.route("/api/reports/<int:report_id>/history", methods=["GET"])
def get_report_history(report_id):
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Verify report ownership or staff access
        cursor.execute("""
            SELECT UserID
            FROM dbo.Reports
            WHERE ReportID = ?
        """, (report_id,))

        report = cursor.fetchone()

        if report is None:
            return jsonify({
                "success": False,
                "error": "Report not found."
            }), 404

        if (
            report.UserID != session["user_id"]
            and session.get("user_role") not in {"Admin", "Authority"}
        ):
            return jsonify({
                "success": False,
                "error": "You are not authorized to view this report."
            }), 403

        cursor.execute("""
            SELECT
                h.PreviousStatus,
                h.NewStatus,
                h.Remarks,
                h.ChangedAt,
                u.FullName AS ChangedByName
            FROM dbo.ReportStatusHistory h
            LEFT JOIN dbo.Users u
                ON h.ChangedBy = u.UserID
            WHERE h.ReportID = ?
            ORDER BY h.ChangedAt DESC, h.HistoryID DESC
        """, (report_id,))

        history = []

        for row in cursor.fetchall():
            history.append({
                "previous_status": row.PreviousStatus,
                "new_status": row.NewStatus,
                "remarks": row.Remarks,
                "changed_at": (
                    row.ChangedAt.isoformat()
                    if row.ChangedAt else None
                ),
                "changed_by": row.ChangedByName
            })

        return jsonify({
            "success": True,
            "report_id": report_id,
            "history": history
        })

    except Exception:
        app.logger.exception("Failed to fetch report status history")

        return jsonify({
            "success": False,
            "error": "Could not load report history."
        }), 500

    finally:
        if connection is not None:
            connection.close()




# ----------------------------------
# Road Risk Scores API
# ----------------------------------

@app.route("/api/road-risk-scores", methods=["GET"])
def get_road_risk_scores():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                s.RoadID,
                r.RoadName,
                r.RoadType,
                r.Latitude,
                r.Longitude,
                s.TotalReports,
                s.RawRiskPoints,
                s.RiskScore,
                s.RiskLevel,
                s.LastCalculatedAt

            FROM dbo.RoadRiskScores AS s

            INNER JOIN dbo.Roads AS r
                ON s.RoadID = r.RoadID

            ORDER BY
                s.RiskScore DESC,
                s.TotalReports DESC
        """)

        risk_scores = []

        for row in cursor.fetchall():

            risk_scores.append({
                "road_id": row.RoadID,
                "road_name": row.RoadName or "Unnamed Road",
                "road_type": row.RoadType,
                "latitude": (
                    float(row.Latitude)
                    if row.Latitude is not None else None
                ),
                "longitude": (
                    float(row.Longitude)
                    if row.Longitude is not None else None
                ),
                "total_reports": row.TotalReports,
                "raw_risk_points": float(row.RawRiskPoints),
                "risk_score": row.RiskScore,
                "risk_level": row.RiskLevel,
                "last_calculated_at": (
                    row.LastCalculatedAt.isoformat()
                    if row.LastCalculatedAt else None
                )
            })

        return jsonify({
            "success": True,
            "total": len(risk_scores),
            "risk_scores": risk_scores
        }), 200

    except Exception:
        app.logger.exception("Failed to retrieve road risk scores")

        return jsonify({
            "success": False,
            "error": "Could not retrieve road risk scores."
        }), 500

    finally:
        if connection is not None:
            connection.close()


# ----------------------------------
# Ward-wise Road Risk Analytics API
# ----------------------------------

@app.route("/api/ward-risk-analytics", methods=["GET"])
def get_ward_risk_analytics():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                rwm.WardNumber,
                COUNT(DISTINCT s.RoadID) AS TotalRiskRoads,
                SUM(s.TotalReports) AS TotalReports,
                MAX(s.RiskScore) AS HighestRiskScore,
                AVG(CAST(s.RiskScore AS FLOAT)) AS AverageRiskScore
            FROM dbo.RoadRiskScores AS s
            INNER JOIN dbo.RoadWardMapping AS rwm
                ON s.RoadID = rwm.RoadID
            GROUP BY rwm.WardNumber
            ORDER BY
                MAX(s.RiskScore) DESC,
                rwm.WardNumber
        """)

        ward_analytics = []

        for row in cursor.fetchall():
            ward_analytics.append({
                "ward_number": row.WardNumber,
                "total_risk_roads": row.TotalRiskRoads,
                "total_reports": row.TotalReports,
                "highest_risk_score": row.HighestRiskScore,
                "average_risk_score": round(
                    float(row.AverageRiskScore), 2
                )
            })

        return jsonify({
            "success": True,
            "total_wards": len(ward_analytics),
            "ward_analytics": ward_analytics
        }), 200

    except Exception:
        app.logger.exception("Failed to retrieve ward risk analytics")

        return jsonify({
            "success": False,
            "error": "Could not retrieve ward risk analytics."
        }), 500

    finally:
        if connection is not None:
            connection.close()



@app.route(
    "/api/reports/<int:report_id>/feedback",
    methods=["POST"]
)
def submit_report_feedback(report_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]

    if session.get("user_role") != "Citizen":
        return jsonify({
            "success": False,
            "error": "Only citizens can submit feedback."
        }), 403

    data = request.get_json(silent=True) or {}

    feedback_status = data.get("feedback_status")
    feedback_message = data.get("feedback_message", "")

    if feedback_status not in {"Solved", "Not Solved"}:
        return jsonify({
            "success": False,
            "error": "Invalid feedback status."
        }), 400

    if not isinstance(feedback_message, str):
        return jsonify({
            "success": False,
            "error": "Feedback message must be text."
        }), 400

    feedback_message = feedback_message.strip()

    if len(feedback_message) > 500:
        return jsonify({
            "success": False,
            "error": "Feedback must be 500 characters or fewer."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT Status
            FROM dbo.Reports
            WHERE ReportID = ?
              AND UserID = ?
        """, (report_id, user_id))

        report = cursor.fetchone()

        if report is None:
            return jsonify({
                "success": False,
                "error": "Report not found."
            }), 404

        if report.Status != "Resolved":
            return jsonify({
                "success": False,
                "error": "Feedback is available only for resolved reports."
            }), 400

        cursor.execute("""
            INSERT INTO dbo.ReportFeedback
                (ReportID, UserID, FeedbackStatus, FeedbackMessage)
            VALUES (?, ?, ?, ?)
        """, (
            report_id,
            user_id,
            feedback_status,
            feedback_message or None
        ))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Feedback submitted successfully."
        }), 201

    except Exception:
        app.logger.exception(
            "Failed to submit feedback for report %s",
            report_id
        )

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Could not submit feedback."
        }), 500

    finally:
        if connection is not None:
            connection.close()



@app.route(
    "/api/reports/<int:report_id>/reopen",
    methods=["POST"]
)
def submit_reopen_request(report_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]

    if session.get("user_role") != "Citizen":
        return jsonify({
            "success": False,
            "error": "Only citizens can request report reopening."
        }), 403

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")

    if not isinstance(reason, str):
        return jsonify({
            "success": False,
            "error": "Invalid request reason."
        }), 400

    reason = reason.strip()

    if not reason or len(reason) > 500:
        return jsonify({
            "success": False,
            "error": "Reason must contain 1 to 500 characters."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT Status
            FROM dbo.Reports
            WHERE ReportID = ?
              AND UserID = ?
        """, (report_id, user_id))

        report = cursor.fetchone()

        if report is None:
            return jsonify({
                "success": False,
                "error": "Report not found."
            }), 404

        if report.Status != "Resolved":
            return jsonify({
                "success": False,
                "error": "Only resolved reports can be reopened."
            }), 400

        cursor.execute("""
            INSERT INTO dbo.ReportReopenRequests
                (ReportID, UserID, RequestReason)
            VALUES (?, ?, ?)
        """, (report_id, user_id, reason))

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Reopen request submitted successfully."
        }), 201

    except Exception as error:
        if connection is not None:
            connection.rollback()

        if "UX_ReopenRequests_Pending" in str(error):
            return jsonify({
                "success": False,
                "error": "A pending reopen request already exists."
            }), 409

        app.logger.exception("Reopen request submission failed.")

        return jsonify({
            "success": False,
            "error": "Could not submit reopen request."
        }), 500

    finally:
        if connection is not None:
            connection.close()


@app.route("/api/authority/reopen-requests", methods=["GET"])
def get_authority_reopen_requests():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_role = session.get("user_role")

    if user_role not in {"Admin", "Authority"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized to view reopen requests."
        }), 403

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                rr.RequestID,
                rr.ReportID,
                rr.UserID,
                u.FullName AS CitizenName,
                rr.RequestReason,
                rr.RequestStatus,
                rr.RequestedAt,
                r.IssueType,
                r.Description,
                r.Status AS ReportStatus

            FROM dbo.ReportReopenRequests rr

            INNER JOIN dbo.Reports r
                ON rr.ReportID = r.ReportID

            INNER JOIN dbo.Users u
                ON rr.UserID = u.UserID

            WHERE rr.RequestStatus = 'Pending'

              AND (
                    ? = 'Admin'

                    OR (
                        ? = 'Authority'

                        AND EXISTS (
                            SELECT 1
                            FROM dbo.ReportAssignments ra

                            INNER JOIN dbo.Authorities a
                                ON ra.AuthorityID = a.AuthorityID

                            WHERE ra.ReportID = rr.ReportID
                              AND ra.AssignmentStatus = 'Assigned'
                              AND a.AuthorityName =
                                  'Rajshahi City Corporation'
                              AND a.IsActive = 1
                        )
                    )
              )

            ORDER BY rr.RequestedAt ASC

        """, (user_role, user_role))

        requests = []

        for row in cursor.fetchall():
            requests.append({
                "request_id": row.RequestID,
                "report_id": row.ReportID,
                "user_id": row.UserID,
                "citizen_name": row.CitizenName,
                "reason": row.RequestReason,
                "request_status": row.RequestStatus,
                "requested_at": (
                    row.RequestedAt.isoformat()
                    if row.RequestedAt else None
                ),
                "issue_type": row.IssueType,
                "description": row.Description,
                "report_status": row.ReportStatus
            })

        return jsonify({
            "success": True,
            "total": len(requests),
            "requests": requests
        }), 200

    except Exception:
        app.logger.exception(
            "Failed to load authority reopen requests."
        )

        return jsonify({
            "success": False,
            "error": "Could not load reopen requests."
        }), 500

    finally:
        if connection is not None:
            connection.close()


@app.route("/api/authority/reopen-requests", methods=["GET"])
def get_reopen_requests():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_role = session.get("user_role", "")

    if user_role not in {"Admin", "Authority"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized to view these requests."
        }), 403

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                rr.RequestID,
                rr.ReportID,
                rr.UserID,
                rr.RequestReason,
                rr.RequestStatus,
                rr.RequestedAt,
                r.IssueType,
                r.Description,
                r.Status AS ReportStatus,
                r.ReportedAt

            FROM dbo.ReportReopenRequests rr

            INNER JOIN dbo.Reports r
                ON rr.ReportID = r.ReportID

            WHERE rr.RequestStatus = 'Pending'

              AND (
                    ? = 'Admin'

                    OR (
                        ? = 'Authority'

                        AND EXISTS (
                            SELECT 1
                            FROM dbo.ReportAssignments ra

                            INNER JOIN dbo.Authorities a
                                ON ra.AuthorityID = a.AuthorityID

                            WHERE ra.ReportID = rr.ReportID
                              AND ra.AssignmentStatus = 'Assigned'
                              AND a.AuthorityName =
                                  'Rajshahi City Corporation'
                              AND a.IsActive = 1
                        )
                    )
              )

            ORDER BY rr.RequestedAt DESC

        """, (user_role, user_role))

        rows = cursor.fetchall()

        requests = []

        for row in rows:
            requests.append({
                "request_id": row.RequestID,
                "report_id": row.ReportID,
                "user_id": row.UserID,
                "reason": row.RequestReason,
                "request_status": row.RequestStatus,
                "requested_at": (
                    row.RequestedAt.isoformat()
                    if row.RequestedAt else None
                ),
                "issue_type": row.IssueType,
                "description": row.Description,
                "report_status": row.ReportStatus,
                "reported_at": (
                    row.ReportedAt.isoformat()
                    if row.ReportedAt else None
                )
            })

        return jsonify({
            "success": True,
            "total": len(requests),
            "requests": requests
        }), 200

    except Exception:
        app.logger.exception(
            "Failed to fetch authority reopen requests."
        )

        return jsonify({
            "success": False,
            "error": "Could not load reopen requests."
        }), 500

    finally:
        if connection is not None:
            connection.close()




@app.route(
    "/api/authority/reopen-requests/<int:request_id>/review",
    methods=["POST"]
)
def review_reopen_request(request_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    user_id = session["user_id"]
    user_role = session.get("user_role")

    if user_role not in {"Admin", "Authority"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized to review requests."
        }), 403

    data = request.get_json(silent=True) or {}

    action = data.get("action")
    remarks = data.get("remarks", "")

    if action not in {"Approved", "Rejected"}:
        return jsonify({
            "success": False,
            "error": "Action must be Approved or Rejected."
        }), 400

    if not isinstance(remarks, str) or len(remarks.strip()) > 500:
        return jsonify({
            "success": False,
            "error": "Remarks must be 500 characters or fewer."
        }), 400

    remarks = remarks.strip()

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                rr.ReportID,
                rr.UserID,
                rr.RequestStatus,
                r.Status AS ReportStatus

            FROM dbo.ReportReopenRequests rr

            INNER JOIN dbo.Reports r
                ON rr.ReportID = r.ReportID

            WHERE rr.RequestID = ?

              AND (
                    ? = 'Admin'

                    OR (
                        ? = 'Authority'

                        AND EXISTS (
                            SELECT 1
                            FROM dbo.ReportAssignments ra

                            INNER JOIN dbo.Authorities a
                                ON ra.AuthorityID = a.AuthorityID

                            WHERE ra.ReportID = rr.ReportID
                              AND ra.AssignmentStatus = 'Assigned'
                              AND a.AuthorityName =
                                  'Rajshahi City Corporation'
                              AND a.IsActive = 1
                        )
                    )
              )

        """, (request_id, user_role, user_role))

        request_row = cursor.fetchone()

        if request_row is None:
            return jsonify({
                "success": False,
                "error": "Request not found or you are not authorized."
            }), 404

        if request_row.RequestStatus != "Pending":
            return jsonify({
                "success": False,
                "error": "This request has already been reviewed."
            }), 409

        report_id = request_row.ReportID
        citizen_user_id = request_row.UserID
        previous_status = request_row.ReportStatus

        if action == "Approved" and previous_status != "Resolved":
            return jsonify({
                "success": False,
                "error": "Only resolved reports can be reopened."
            }), 409

        cursor.execute("""
            UPDATE dbo.ReportReopenRequests
            SET
                RequestStatus = ?,
                ReviewedBy = ?,
                AuthorityRemarks = ?,
                ReviewedAt = SYSUTCDATETIME()
            WHERE RequestID = ?
              AND RequestStatus = 'Pending'
        """, (
            action,
            user_id,
            remarks or None,
            request_id
        ))

        if cursor.rowcount == 0:
            connection.rollback()

            return jsonify({
                "success": False,
                "error": "This request has already been reviewed."
            }), 409

        if action == "Approved":

            new_status = "In Progress"

            cursor.execute("""
                UPDATE dbo.Reports
                SET Status = ?
                WHERE ReportID = ?
            """, (new_status, report_id))

            cursor.execute("""
                INSERT INTO dbo.ReportStatusHistory
                    (
                        ReportID,
                        PreviousStatus,
                        NewStatus,
                        ChangedBy,
                        Remarks,
                        ChangedAt
                    )
                VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME())
            """, (
                report_id,
                previous_status,
                new_status,
                user_id,
                remarks or "Report reopened after citizen request."
            ))

            notification_title = "Your Reopen Request Was Approved"

            notification_message = (
                f"Your reopen request for report #{report_id} "
                "has been approved. The report is now In Progress."
            )

        else:

            notification_title = "Your Reopen Request Was Rejected"

            notification_message = (
                f"Your reopen request for report #{report_id} "
                "has been rejected."
            )

            if remarks:
                notification_message += f" Authority remarks: {remarks}"

        cursor.execute("""
            INSERT INTO dbo.Notifications
                (UserID, ReportID, Title, Message)
            VALUES (?, ?, ?, ?)
        """, (
            citizen_user_id,
            report_id,
            notification_title,
            notification_message
        ))

        connection.commit()

        return jsonify({
            "success": True,
            "message": (
                "Reopen request approved successfully."
                if action == "Approved"
                else "Reopen request rejected successfully."
            ),
            "request_id": request_id,
            "report_id": report_id,
            "request_status": action
        }), 200

    except Exception:
        if connection is not None:
            connection.rollback()

        app.logger.exception(
            "Failed to review reopen request %s",
            request_id
        )

        return jsonify({
            "success": False,
            "error": "Could not review reopen request."
        }), 500

    finally:
        if connection is not None:
            connection.close()





# ----------------------------------
# Ward-wise Roads API
# ----------------------------------

@app.route("/api/wards/<int:ward_number>/roads")
def get_ward_roads(ward_number):

    if ward_number < 1 or ward_number > 30:
        return jsonify({
            "success": False,
            "error": "Invalid ward number."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                r.RoadID,
                r.OSMID,
                r.RoadName,
                r.RoadType,
                r.Latitude,
                r.Longitude,
                rwm.WardNumber,
                rwm.WardCode
            FROM dbo.Roads AS r
            INNER JOIN dbo.RoadWardMapping AS rwm
                ON r.RoadID = rwm.RoadID
            WHERE rwm.WardNumber = ?
            ORDER BY r.RoadID
        """, (str(ward_number),))

        columns = [
            column[0]
            for column in cursor.description
        ]

        roads = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return jsonify({
            "success": True,
            "ward_number": ward_number,
            "total": len(roads),
            "roads": roads
        })

    except Exception:
        app.logger.exception(
            "Failed to retrieve roads for Ward %s",
            ward_number
        )

        return jsonify({
            "success": False,
            "error": "Could not retrieve ward road data."
        }), 500

    finally:
        if connection is not None:
            connection.close()




@app.route("/api/roads")
def get_roads():

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                RoadID,
                OSMID,
                RoadName,
                RoadType,
                Latitude,
                Longitude
            FROM dbo.Roads
            ORDER BY RoadID
        """)

        columns = [
            column[0]
            for column in cursor.description
        ]

        roads = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

        return jsonify({
            "total": len(roads),
            "roads": roads
        })

    except Exception:
        app.logger.exception("Failed to retrieve roads")

        return jsonify({
            "error": "Could not retrieve road data from the database."
        }), 500

    finally:
        if connection is not None:
            connection.close()





# ----------------------------------------
# Nearby Road Geometry API for Map
# ----------------------------------------

@app.route(
    "/api/reports/<int:report_id>/nearby-roads",
    methods=["GET"]
)
def get_nearby_roads(report_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    if session.get("user_role") not in {"Authority", "Admin"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized."
        }), 403

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Verify report and authority permission
        cursor.execute("""
            SELECT
                r.Latitude,
                r.Longitude,
                r.RoadID
            FROM dbo.Reports r
            WHERE r.ReportID = ?
              AND (
                    ? = 'Admin'
                    OR EXISTS (
                        SELECT 1
                        FROM dbo.ReportAssignments ra
                        INNER JOIN dbo.Authorities a
                            ON ra.AuthorityID = a.AuthorityID
                        WHERE ra.ReportID = r.ReportID
                          AND ra.AssignmentStatus = 'Assigned'
                          AND a.AuthorityName =
                              'Rajshahi City Corporation'
                          AND a.IsActive = 1
                    )
              )
        """, (
            report_id,
            session.get("user_role")
        ))

        report = cursor.fetchone()

        if report is None:
            return jsonify({
                "success": False,
                "error": "Report not found or not authorized."
            }), 404

        if report.RoadID is not None:
            return jsonify({
                "success": False,
                "error": "This report already has an assigned road."
            }), 409

        if report.Latitude is None or report.Longitude is None:
            return jsonify({
                "success": False,
                "error": "Report location is unavailable."
            }), 400

        latitude = float(report.Latitude)
        longitude = float(report.Longitude)

        # Convert report location into meters
        x, y = projector.transform(longitude, latitude)
        report_point = Point(x, y)

        # Load actual road geometries
        roads = load_roads()

        nearby = []

        for road in roads:

            distance = report_point.distance(
                road["geometry"]
            )

            if distance <= 200:
                nearby.append({
                    "osm_id": road["OSMID"],
                    "distance": distance,
                    "geometry": road["geojson_geometry"]
                })

        nearby.sort(key=lambda item: item["distance"])
        nearby = nearby[:15]

        if not nearby:
            return jsonify({
                "success": True,
                "report_location": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "roads": []
            }), 200

        # Match OSM IDs with database RoadIDs
        osm_ids = [road["osm_id"] for road in nearby]

        placeholders = ",".join(
            ["?"] * len(osm_ids)
        )

        cursor.execute(f"""
            SELECT
                RoadID,
                OSMID,
                RoadName,
                RoadType
            FROM dbo.Roads
            WHERE OSMID IN ({placeholders})
        """, osm_ids)

        road_lookup = {
            row.OSMID: {
                "road_id": row.RoadID,
                "road_name": row.RoadName or "Unnamed Road",
                "road_type": row.RoadType
            }
            for row in cursor.fetchall()
        }

        features = []

        for road in nearby:

            details = road_lookup.get(road["osm_id"])

            if not details:
                continue

            features.append({
                "type": "Feature",
                "geometry": road["geometry"],
                "properties": {
                    **details,
                    "osm_id": road["osm_id"],
                    "distance_m": round(
                        road["distance"], 2
                    )
                }
            })

        return jsonify({
            "success": True,
            "report_location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "total": len(features),
            "roads": {
                "type": "FeatureCollection",
                "features": features
            }
        }), 200

    except Exception:

        app.logger.exception(
            "Nearby road geometry API failed for report %s",
            report_id
        )

        return jsonify({
            "success": False,
            "error": "Could not retrieve nearby roads."
        }), 500

    finally:
        if connection is not None:
            connection.close()



    



# ----------------------------------------
# Search Roads API for Authority Assignment
# ----------------------------------------

@app.route("/api/roads/search", methods=["GET"])
def search_roads():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify({
            "success": True,
            "roads": []
        })

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        search_term = f"%{query}%"

        cursor.execute("""
            SELECT TOP 20
                RoadID,
                OSMID,
                RoadName,
                RoadType
            FROM dbo.Roads
            WHERE
                CAST(OSMID AS NVARCHAR(50)) LIKE ?
                OR RoadName LIKE ?
                OR RoadType LIKE ?
            ORDER BY RoadID
        """, (
            search_term,
            search_term,
            search_term
        ))

        roads = []

        for row in cursor.fetchall():
            roads.append({
                "road_id": row.RoadID,
                "osm_id": row.OSMID,
                "road_name": row.RoadName or "Unnamed Road",
                "road_type": row.RoadType
            })

        return jsonify({
            "success": True,
            "roads": roads
        })

    except Exception:
        app.logger.exception("Road search failed")

        return jsonify({
            "success": False,
            "error": "Could not search roads."
        }), 500

    finally:
        if connection is not None:
            connection.close()



# ----------------------------------------
# Assign Report to a Road API
# ----------------------------------------

@app.route(
    "/api/reports/<int:report_id>/assign-road",
    methods=["POST"]
)
def assign_report_to_road(report_id):

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    if session.get("user_role") not in {"Authority", "Admin"}:
        return jsonify({
            "success": False,
            "error": "You are not authorized."
        }), 403

    data = request.get_json(silent=True) or {}
    road_id = data.get("road_id")

    try:
        road_id = int(road_id)
        if road_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Please select a valid road."
        }), 400

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Verify report and authority assignment
        cursor.execute("""
    SELECT
        r.RoadID,
        r.WardNumber
    FROM dbo.Reports r
            WHERE r.ReportID = ?
              AND (
                    ? = 'Admin'
                    OR EXISTS (
                        SELECT 1
                        FROM dbo.ReportAssignments ra
                        INNER JOIN dbo.Authorities a
                            ON ra.AuthorityID = a.AuthorityID
                        WHERE ra.ReportID = r.ReportID
                          AND ra.AssignmentStatus = 'Assigned'
                          AND a.AuthorityName =
                              'Rajshahi City Corporation'
                          AND a.IsActive = 1
                    )
              )
        """, (
            report_id,
            session.get("user_role")
        ))

        report = cursor.fetchone()

        if report is None:
            return jsonify({
                "success": False,
                "error": "Report not found or not authorized."
            }), 404

        if report.RoadID is not None:
            return jsonify({
                "success": False,
                "error": "This report is already assigned to a road."
            }), 409





        # Verify report and road ward
        if report.WardNumber is None:
            return jsonify({
                "success": False,
                "error": "Report ward information is unavailable."
            }), 400

        cursor.execute("""
            SELECT WardNumber
            FROM dbo.RoadWardMapping
            WHERE RoadID = ?
        """, (road_id,))

        road_ward = cursor.fetchone()

        if road_ward is None:
            return jsonify({
                "success": False,
                "error": "This road is not mapped to an RCC ward."
            }), 400

        if str(report.WardNumber).strip() != str(road_ward.WardNumber).strip():
            return jsonify({
                "success": False,
                "error": (
                    f"Ward mismatch! Report is in Ward "
                    f"{report.WardNumber}, but selected road belongs to "
                    f"Ward {road_ward.WardNumber}."
                )
            }), 400

        

        # Verify selected road
        cursor.execute("""
            SELECT RoadID
            FROM dbo.Roads
            WHERE RoadID = ?
        """, (road_id,))

        if cursor.fetchone() is None:
            return jsonify({
                "success": False,
                "error": "Selected road was not found."
            }), 404

        # Assign road to report
        cursor.execute("""
            UPDATE dbo.Reports
            SET RoadID = ?
            WHERE ReportID = ?
              AND RoadID IS NULL
        """, (road_id, report_id))

        if cursor.rowcount != 1:
            raise Exception("Report assignment could not be completed.")

        # Recalculate road risk score
        update_road_risk_score(cursor, road_id)

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Road assigned successfully.",
            "report_id": report_id,
            "road_id": road_id
        }), 200

    except Exception:
        app.logger.exception(
            "Road assignment failed for report ID %s",
            report_id
        )

        if connection is not None:
            connection.rollback()

        return jsonify({
            "success": False,
            "error": "Could not assign road to this report."
        }), 500

    finally:
        if connection is not None:
            connection.close()








# ----------------------------------------
# Road Condition Overview API
# ----------------------------------------

@app.route("/api/road-condition-overview", methods=["GET"])
def get_road_condition_overview():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Please sign in first."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # 1. Road Risk Distribution
        cursor.execute("""
            SELECT
                RiskLevel,
                COUNT(*) AS TotalRoads
            FROM dbo.RoadRiskScores
            GROUP BY RiskLevel
            ORDER BY TotalRoads DESC
        """)

        risk_distribution = []

        for row in cursor.fetchall():
            risk_distribution.append({
                "risk_level": row.RiskLevel,
                "total_roads": row.TotalRoads
            })

        # 2. Most Reported Issues
        cursor.execute("""
            SELECT
                IssueType,
                COUNT(*) AS TotalReports
            FROM dbo.Reports
            GROUP BY IssueType
            ORDER BY TotalReports DESC
        """)

        most_reported_issues = []

        for row in cursor.fetchall():
            most_reported_issues.append({
                "issue_type": row.IssueType,
                "total_reports": row.TotalReports
            })

        return jsonify({
            "success": True,
            "risk_distribution": risk_distribution,
            "most_reported_issues": most_reported_issues
        })

    except Exception:
        app.logger.exception(
            "Road Condition Overview API failed"
        )

        return jsonify({
            "success": False,
            "error": "Could not load road condition overview."
        }), 500

    finally:
        if connection is not None:
            connection.close()



# ----------------------------------
# Authority Overview API
# ----------------------------------

@app.route("/api/authority-overview", methods=["GET"])
def get_authority_overview():

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "error": "Authentication required."
        }), 401

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # 1. Authority Profile and Performance
        cursor.execute("""
            SELECT
                MIN(a.AuthorityID) AS AuthorityID,
                a.AuthorityName,
                a.Department,
                a.City,
                a.ContactEmail,
                a.ContactPhone,

                COUNT(ra.AssignmentID) AS TotalAssignments,

                COUNT(DISTINCT ra.ReportID)
                    AS UniqueAssignedReports,

                SUM(
                    CASE
                        WHEN ra.AssignmentStatus = 'Assigned'
                        THEN 1
                        ELSE 0
                    END
                ) AS ActiveAssignments

            FROM dbo.Authorities a

            LEFT JOIN dbo.ReportAssignments ra
                ON a.AuthorityID = ra.AuthorityID

            WHERE a.IsActive = 1

            GROUP BY
               
                a.AuthorityName,
                a.Department,
                a.City,
                a.ContactEmail,
                a.ContactPhone
        """)

        authority_row = cursor.fetchone()

        if authority_row is None:
            return jsonify({
                "success": True,
                "authority": None,
                "recent_assignments": []
            })

        authority = {
            "authority_id": authority_row.AuthorityID,
            "authority_name": authority_row.AuthorityName,
            "department": authority_row.Department,
            "city": authority_row.City,
            "contact_email": authority_row.ContactEmail,
            "contact_phone": authority_row.ContactPhone,
            "total_assignments": authority_row.TotalAssignments or 0,
            "unique_assigned_reports":
                authority_row.UniqueAssignedReports or 0,
            "active_assignments":
                authority_row.ActiveAssignments or 0
        }

        # 2. Recent Authority Assignments
        cursor.execute("""
            SELECT TOP 5
                ra.ReportID,
                r.IssueType,
                ra.AssignedAt,
                ra.AssignmentStatus,
                ra.Remarks

            FROM dbo.ReportAssignments ra

            INNER JOIN dbo.Reports r
                ON ra.ReportID = r.ReportID
            WHERE ra.AuthorityID IN (
                SELECT AuthorityID
                FROM dbo.Authorities
                WHERE AuthorityName = ?
                AND Department = ?
                AND City = ?
                AND IsActive = 1
            )
            
            ORDER BY ra.AssignedAt DESC
        """, (
            authority["authority_name"],
            authority["department"],
            authority["city"]
        ))

        recent_assignments = []

        for row in cursor.fetchall():
            recent_assignments.append({
                "report_id": row.ReportID,
                "issue_type": row.IssueType,
                "assigned_at": (
                    row.AssignedAt.isoformat()
                    if row.AssignedAt else None
                ),
                "assignment_status": row.AssignmentStatus,
                "remarks": row.Remarks
            })

        return jsonify({
            "success": True,
            "authority": authority,
            "recent_assignments": recent_assignments
        })

    except Exception:
        app.logger.exception(
            "Authority Overview API failed"
        )

        return jsonify({
            "success": False,
            "error": "Could not load authority information."
        }), 500

    finally:
        if connection is not None:
            connection.close()








# ----------------------------------
# Run application
# ----------------------------------

if __name__ == "__main__":
    app.run(debug=os.environ.get("APP_ENV") != "production")