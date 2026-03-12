import os

os.makedirs(".streamlit", exist_ok=True)

secrets = '''[gcp_service_account]
type = "service_account"
project_id = "firm-harbor-469514-g6"
private_key_id = "7112a968932555ade44bfcf346f02c3c1498afbe"
private_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCyOA0MMk2qmw7l
36L8JO1tKnNdUD5201ShZt6rWa9D7lIhGeVL14El5HxKEPDUgsCAnfHe2yLTQhMF
vLa1mmm255zpleaGLA3RUEBsEVabnkjzEHL1PgrJkNI2Wh+3M8efslFjiJBZquMC
SPL9dxvu+AVSLBrOUAudxon/7QqrOlIt/sMtTqSU1bhojgcWfgd9tJ0kWbi3bQty
AJrlsJTyrXupD4wuJ/m4mQA53gpX1jyqSgvXkGjH10iskgzYcmgn4+Htk3XlzKyT
miNZI7S4XS+mb1cxhWKT3sWg7Rs0BUAwzjaSieXuemSM3ZNI7XPASdJmtMtmxKwA
YhKiLuVTAgMBAAECggEABS+wDYP556DrM5Go/rkdDFljvGTv6b78+P9zM72rOzOt
wdcs6Y1EGF6y++gh91qLZegdbZ9R6Z+ZdHLJRwqkez/35yzyEEMq7xrsl63U0o2D
e537F8ZDmRm09wOeEFOaQmb1iwsigZbWqVkxx7eAzBj9Sqa27FG/AiCQy9j8P6mp
N3LWabzauiBMO16jtgADkYxXUaTvs6p7/qfzMRdza2Ctvv9wBBkidvEwbrEG2NPo
kNuSIAYRCxpDuQtxbg30x5hAThHMOIacasfNuQbBYOW2NCzru7MV4T7fOpoASKzb
7lT/2EXBSC7Rgfi7/X5VFPgx8mdbKBwGB1bvxP5NMQKBgQDcZ0943JxDHtrWHReo
AIuvHXLJvCtZKQZu9AW6OvOBrXkIrtRxmIvpM1svca3b97WNIWZQLy9j3+DbURit
QjBGIBsRtuCkybJHwjLXYok60hU5e6D5TKwp2QxPlbf7f110iJ4goORXNtTDgjSw
G1DKO0eTlwzSSfg3t/3GbPpQwwKBgQDPAJkSQ40RwL47FpII0um+yRpybWd8lMB1
Am2e0kAVMehBtqp39ZYsHe4wXsFvkF8juGOLkXHPtKrmtHgUSLA5Zu1nlSkf3BNJ
ifxQhw+PcgZ8/prsit8Myr1HSlUE27g/NC1gm1K1I1TGOrRB5FiNbMPtyi3cJUxQ
CVpT3k3QMQKBgHxkYloYSKkpNOE7MirDhBKlUC/DX8PGf7cHSmQ8+UnrGjBoW8Zx
DiXjskcopbNMLs8kVpZSyzBXHpUpRAAlJxGs9RoeWNMoctJFLGSbXFAyWYBD4ipR
t6k2stgH6/qpe5lVsclAhR8j9xkQ16O9Bu/cXR1TVw0oaksoMLZYsz35AoGBAJaZ
mMPw4XFJCR10DkrdJ7HmHZeigOfiUSLP4XDrBjRlWtR0URF1Www9ukz2o0THhHA4
djPUXTj/+FZgdfxL5endOFtj6ceEFYQrH6Z2nJuAGbhWg+AUKLLlzU9QhQpD0Igr
LdhbKJEgY0zU6NAHkWVS/DjEHxlLCXoxU8YwtewBAoGAJBcTkhl76T7ROumg+iyH
8s79/GiqsTZ59wIZGt4cFWXHJ9o55+eAy5pL+NHfIsdyPW5XS3H9g4a5mzybyhpV
58asUJkPxjjuKLdpNHbXmYB6bIjnbysKk76t/Smx/PIsZCB2m0gdF0ZeBdrXtLOP
b+3E9NXqy2fKaLmlmjJc4LQ=
-----END PRIVATE KEY-----"""
client_email = "meta-leads@firm-harbor-469514-g6.iam.gserviceaccount.com"
client_id = "118245169860457891423"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
'''

with open(".streamlit/secrets.toml", "w") as f:
    f.write(secrets)

print("secrets.toml created!")