import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Inizializza l'app Firebase
cred = credentials.Certificate('config_fb.json')

options = {
    'databaseURL': 'https://nextercare-x-default-rtdb.europe-west1.firebasedatabase.app'
}

def write_data_to_firebase_realtime(data, path):
    realtime_app = initialize_firebase_app(cred, "firebase-realtime-app", options)
    # Ottieni un riferimento al nodo del database su cui vuoi scrivere
    realtime_db = db.reference(
        path, app=realtime_app)

    # Scrivi i dati nel nodo del database

    realtime_db.update(data)

    # Chiudi l'app Firebase (opzionale)
    firebase_admin.delete_app(realtime_app)

def initialize_firebase_app(cred, app_name, options=None):
    # Check if the app has already been initialized
    try:
        return firebase_admin.get_app(app_name)
    except ValueError:
        # If not initialized, then initialize now
        return firebase_admin.initialize_app(credential=cred, options=options, name=app_name)

def delete_data_from_firebase_realtime(path):
    realtime_app = initialize_firebase_app(cred, "firebase-realtime-app", options)
    # Ottieni un riferimento al nodo del database su cui vuoi scrivere
    realtime_db = db.reference(
        path, app=realtime_app)

    # Scrivi i dati nel nodo del database

    realtime_db.delete()

    # Chiudi l'app Firebase (opzionale)
    firebase_admin.delete_app(realtime_app)
