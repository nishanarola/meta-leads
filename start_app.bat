@echo off
echo ================================
echo    Enacle Leads App Starting...
echo ================================

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Downloading...
    curl -o python_installer.exe https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe
    echo Installing Python...
    python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del python_installer.exe
)

:: Create .streamlit folder and secrets.toml
if not exist ".streamlit" mkdir .streamlit
if not exist ".streamlit\secrets.toml" (
    echo Creating secrets...
    (
        echo [gcp_service_account]
        echo type = "service_account"
        echo project_id = "firm-harbor-469514-g6"
        echo private_key_id = "7112a968932555ade44bfcf346f02c3c1498afbe"
        echo private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCyOA0MMk2qmw7l\n36L8JO1tKnNdUD5201ShZt6rWa9D7lIhGeVL14El5HxKEPDUgsCAnfHe2yLTQhMF\nvLa1mmm255zpleaGLA3RUEBsEVabnkjzEHL1PgrJkNI2Wh+3M8efslFjiJBZquMC\nSPL9dxvu+AVSLBrOUAudxon/7QqrOlIt/sMtTqSU1bhojgcWfgd9tJ0kWbi3bQty\nAJrlsJTyrXupD4wuJ/m4mQA53gpX1jyqSgvXkGjH10iskgzYcmgn4+Htk3XlzKyT\nmiNZI7S4XS+mb1cxhWKT3sWg7Rs0BUAwzjaSieXuemSM3ZNI7XPASdJmtMtmxKwA\nYhKiLuVTAgMBAAECggEABS+wDYP556DrM5Go/rkdDFljvGTv6b78+P9zM72rOzOt\nwdcs6Y1EGF6y++gh91qLZegdbZ9R6Z+ZdHLJRwqkez/35yzyEEMq7xrsl63U0o2D\ne537F8ZDmRm09wOeEFOaQmb1iwsigZbWqVkxx7eAzBj9Sqa27FG/AiCQy9j8P6mp\nN3LWabzauiBMO16jtgADkYxXUaTvs6p7/qfzMRdza2Ctvv9wBBkidvEwbrEG2NPo\nkNuSIAYRCxpDuQtxbg30x5hAThHMOIacasfNuQbBYOW2NCzru7MV4T7fOpoASKzb\n7lT/2EXBSC7Rgfi7/X5VFPgx8mdbKBwGB1bvxP5NMQKBgQDcZ0943JxDHtrWHReo\nAIuvHXLJvCtZKQZu9AW6OvOBrXkIrtRxmIvpM1svca3b97WNIWZQLy9j3+DbURit\nQjBGIBsRtuCkybJHwjLXYok60hU5e6D5TKwp2QxPlbf7f110iJ4goORXNtTDgjSw\nG1DKO0eTlwzSSfg3t/3GbPpQwwKBgQDPAJkSQ40RwL47FpII0um+yRpybWd8lMB1\nAm2e0kAVMehBtqp39ZYsHe4wXsFvkF8juGOLkXHPtKrmtHgUSLA5Zu1nlSkf3BNJ\nifxQhw+PcgZ8/prsit8Myr1HSlUE27g/NC1gm1K1I1TGOrRB5FiNbMPtyi3cJUxQ\nCVpT3k3QMQKBgHxkYloYSKkpNOE7MirDhBKlUC/DX8PGf7cHSmQ8+UnrGjBoW8Zx\nDiXjskcopbNMLs8kVpZSyzBXHpUpRAAlJxGs9RoeWNMoctJFLGSbXFAyWYBD4ipR\nt6k2stgH6/qpe5lVsclAhR8j9xkQ16O9Bu/cXR1TVw0oaksoMLZYsz35AoGBAJaZ\nmMPw4XFJCR10DkrdJ7HmHZeigOfiUSLP4XDrBjRlWtR0URF1Www9ukz2o0THhHA4\ndjPUXTj/+FZgdfxL5endOFtj6ceEFYQrH6Z2nJuAGbhWg+AUKLLlzU9QhQpD0Igr\nLdhbKJEgY0zU6NAHkWVS/DjEHxlLCXoxU8YwtewBAoGAJBcTkhl76T7ROumg+iyH\n8s79/GiqsTZ59wIZGt4cFWXHJ9o55+eAy5pL+NHfIsdyPW5XS3H9g4a5mzybyhpV\n58asUJkPxjjuKLdpNHbXmYB6bIjnbysKk76t/Smx/PIsZCB2m0gdF0ZeBdrXtLOP\nb+3E9NXqy2fKaLmlmjJc4LQ=\n-----END PRIVATE KEY-----\n"
        echo client_email = "meta-leads@firm-harbor-469514-g6.iam.gserviceaccount.com"
        echo client_id = "118245169860457891423"
        echo auth_uri = "https://accounts.google.com/o/oauth2/auth"
        echo token_uri = "https://oauth2.googleapis.com/token"
    ) > .streamlit\secrets.toml
)

