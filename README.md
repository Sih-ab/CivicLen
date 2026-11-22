# CivicLen — Rajshahi Road Intelligence

### Connecting Every Road to a Better Tomorrow.

**CivicLen** is a web-based road monitoring and reporting platform designed to improve road management and citizen engagement within Rajshahi City Corporation (RCC), Bangladesh.

It allows citizens to search for roads, report road-related problems, and monitor report status. Authorities can manage assigned reports, review road conditions, and update report statuses through a dedicated dashboard.

## 🌐 Live Website

**[Visit CivicLen — Live Application](https://civiclen-app-c5eyhacudbcpg4bv.centralindia-01.azurewebsites.net)**

## 🎯 Project Objectives

- Improve road issue reporting and monitoring.
- Connect citizens with responsible authorities.
- Provide road information through an interactive platform.
- Support efficient report management and tracking.
- Improve transparency in road maintenance activities.

## ✨ Key Features

### Citizen Panel
- User registration and login.
- Road search functionality.
- Interactive road map.
- Road issue reporting.
- Report status tracking.

### Authority Dashboard
- Assigned report management.
- Report search and filtering.
- Report status updates.
- Report monitoring and management.

### Road Intelligence
- 5,254 road records.
- Road-to-ward mapping.
- Road risk scoring.
- Geographic road information.

## 🗺️ Project Coverage

**Geographical Scope:** Rajshahi City Corporation, Bangladesh.

The project focuses exclusively on roads within the Rajshahi City Corporation boundary.

## 🛠️ Technologies Used

| Category | Technologies |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript |
| Database | Microsoft SQL Server, Azure SQL Database |
| Database Connectivity | PyODBC |
| Geospatial Processing | Shapely, PyProj |
| Cloud Hosting | Microsoft Azure App Service |
| Version Control | Git, GitHub |

## 🏗️ System Architecture

```text
       Citizens / Authorities
                 |
                 v
          Web Application
                 |
                 v
          Flask Backend
                 |
                 v
          PyODBC Connectivity
                 |
                 v
          Azure SQL Database
                 |
                 v
          Roads / Reports /
          Users / Authorities
```

## 📊 Database Overview

The application uses Microsoft SQL Server and Azure SQL Database.

Major database tables include:

- Users
- Roads
- Reports
- Authorities
- RoadWardMapping
- ReportStatusHistory
- RoadRiskScores
- ReportAssignments
- Notifications

## 🚀 Local Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Sih-ab/CivicLen.git
```

### 2. Navigate to the Project Folder

```bash
cd CivicLen
```

### 3. Create a Virtual Environment

```bash
python -m venv venv
```

### 4. Activate the Environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Configure the required database connection and Flask secret key through environment variables.

Required variables:

- `FLASK_SECRET_KEY`
- `AZURE_SQL_CONNECTION_STRING`

For local development, configure the appropriate database connection.

### 7. Run the Application

```bash
python app.py
```

Open your browser:

```text
http://127.0.0.1:5000
```

## ☁️ Deployment

CivicLen is deployed using **Microsoft Azure App Service** with an Azure SQL Database backend.

Live Application:

https://civiclen-app-c5eyhacudbcpg4bv.centralindia-01.azurewebsites.net

## 👨‍💻 Developer

**MD. Sihab Hossen**

GitHub: [Sih-ab](https://github.com/Sih-ab)

## 🔮 Future Improvements

- Advanced road condition analytics.
- Improved geospatial visualization.
- Enhanced notification system.
- Additional road maintenance insights.
- Improved reporting and performance analytics.

---

**CivicLen — Connecting Every Road to a Better Tomorrow.**