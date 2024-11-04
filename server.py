import asyncio
import aiocoap
import aiocoap.resource as resource
import random
import aiohttp
from aiohttp import web
import sys
import aiofiles
import subprocess
import threading
import re
import requests
import shutil
import sqlite3

# utility
import json
import netifaces
import datetime
import os
import pytz, tzlocal
import time

#from google.cloud import firestore

# importo file per scrittura dati real time
from configuration_positioning import CalibrateData 
from database_manager import DatabaseManager 

context = None
conn = None
dizionario_globale = {}
dizionario_globale_timestamp = {}
brssi = {}
ipv6_wpan0 = ""
brssi_freq = 1 * 60 # 1 min in secondi
update_time_freq = 2 * 60 *  60 # ore in secondi
brip_freq = 5 # min
addjoiner_endpoint = 'http://localhost:5000/openthread/addjoiner'
updatetime_endpoint = 'http://localhost:5000/updatetime'
getlatestv_endpoint = 'http://localhost:5000/getlatestv'
host_url = "http://127.0.0.1:9999"
start_path = ""
database = start_path + "/shared_dir/DATISTORICI.db"
database_positioning =  start_path + "/shared_dir/positioning.db"
config_filename = start_path+"/shared_dir/config.json"
log_filename = start_path+"/shared_dir/log.json"
coap_brssi_filename = start_path+"/shared_dir/coap_brssi.json"
bs02_data_filename = start_path+"/shared_dir/deviceData.json"

is_updating = False
cleaning_data_flag = False
calibrating = False

diceface = {}
ipv6logs = {}

# Funzione per creare una connessione al database SQLite
def create_connection(db_file):
    conn = None
    try:
        db_exists = os.path.isfile(db_file)
        conn = sqlite3.connect(db_file)
        custom_print(f"Connessione al database {db_file} avvenuta con successo")
        if not db_exists:
            os.chmod(db_file, 0o777)
            custom_print(f"Permessi del database {db_file} modificati a 777")
    except sqlite3.Error as e:
        custom_print(f"Errore durante la connessione al database: {e}")
    return conn

# Funzione per creare le tabelle se non esistono
def create_tables(conn):
    try:
        sql_create_logdevices_table = """
        CREATE TABLE IF NOT EXISTS logdevices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT,
            type TEXT,
            timestamp TEXT
        );"""
        sql_create_diceface_table = """
        CREATE TABLE IF NOT EXISTS diceface (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT,
            face TEXT,
            timestamp TEXT
        );"""
        sql_create_livedatabangle_table = """
        CREATE TABLE IF NOT EXISTS datilive_bangle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT NOT NULL,
            timestampInizio TEXT,
            timestampFine TEXT,
            type TEXT,
            timestamp TEXT
        );"""
        sql_create_puck_table = """
        CREATE TABLE IF NOT EXISTS datistorici_puck (
            mac TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            mov TEXT,
            l TEXT,
            t TEXT,
            UNIQUE(mac, timestamp)
        );"""
        sql_create_puck_positioning = """
        CREATE TABLE IF NOT EXISTS datistorici_positioning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            macBs02 TEXT,
            macBangle TEXT,
            rssiBangle TEXT
        );"""
        sql_create_bs02_table = """
        CREATE TABLE IF NOT EXISTS datistorici_bs02 (
            mac TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            h TEXT,
            t TEXT,
            l TEXT,
            c TEXT,
            UNIQUE(mac, timestamp)
        );"""
        sql_create_bangle_table = """
        CREATE TABLE IF NOT EXISTS datistorici_bangle (
            mac TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            bpm TEXT,
            min TEXT,
            max TEXT,
            l TEXT,
            c TEXT,
            t TEXT,
            p TEXT,
            a TEXT,
            s TEXT,
            nr TEXT,
            mad TEXT,
            v TEXT,
            b TEXT,
            rs TEXT,
            UNIQUE(mac, timestamp)
        );"""
        
        conn.execute(sql_create_puck_table)
        conn.execute(sql_create_bs02_table)
        conn.execute(sql_create_bangle_table)
        conn.execute(sql_create_puck_positioning)
        conn.execute(sql_create_livedatabangle_table)
        conn.execute(sql_create_diceface_table)
        conn.execute(sql_create_logdevices_table)
        
        custom_print("Tabelle create con successo (se non esistevano già)")
    except sqlite3.Error as e:
        custom_print(f"Errore durante la creazione delle tabelle: {e}")
        
        
# Funzione per inserire i dati nella tabella logdevices
def insert_data_logdevices(conn, data_dict):
    try:
        sql_insert = "INSERT INTO logdevices (mac, type, timestamp) VALUES (?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None),
            data_dict.get("type", None),
            data_dict.get("timestamp", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'logdevices'")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati logdevices: {e}")

# Funzione per inserire i dati nella tabella diceface
def insert_data_diceface(conn, data_dict):
    try:
        sql_insert = "INSERT INTO diceface (mac, face, timestamp) VALUES (?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None), 
            data_dict.get("face", None), 
            data_dict.get("timestamp", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'diceface'")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati diceface: {e}")


# Funzione per inserire i dati nella tabella puck
def insert_data_puck(conn, data_dict):
    try:
        sql_insert = "INSERT INTO datistorici_puck (mac, timestamp, mov, l, t) VALUES (?, ?, ?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None), 
            data_dict.get("rts", None), 
            data_dict.get("mov", None), 
            data_dict.get("l", None), 
            data_dict.get("t", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'datistorici_puck'")
    except sqlite3.IntegrityError:
        custom_print("Errore: Duplicato trovato per (mac, timestamp). Dati non inseriti.")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati puck: {e}")

# Funzione per inserire i dati nella tabella livedatabangle
def insert_data_livedatabangle(conn, data_dict):
    try:
        sql_insert = "INSERT INTO datilive_bangle (mac, timestampInizio, timestampFine, type, timestamp) VALUES (?, ?, ?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None), 
            data_dict.get("timestampInizio", None), 
            data_dict.get("timestampFine", None), 
            data_dict.get("type", None),
            data_dict.get("timestamp", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'datilive_bangle'")
    except sqlite3.IntegrityError:
        custom_print("Errore: Duplicato trovato per (id). Dati non inseriti.")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati datilive_bangle: {e}")
        
# Funzione per inserire i dati nella tabella positioning
def insert_data_positioning(conn, data_list):
	try:
		for data_dict in data_list:
			try:
				sql_insert = "INSERT INTO datistorici_positioning (timestamp, macBs02, macBangle, rssiBangle) VALUES (?, ?, ?, ?)"
				cur = conn.cursor()
				cur.execute(sql_insert, (
					data_dict.get("timestamp", None), 
					data_dict.get("macBs02", None), 
					data_dict.get("macBangle", None), 
					data_dict.get("rssiBangle", None), 
				))
				conn.commit()
			except sqlite3.IntegrityError:
				custom_print("Errore: Duplicato trovato per (id). Dati non inseriti.")
			except sqlite3.Error as e:
				custom_print(f"Errore durante l'inserimento dei dati sul positioning: {e}")
		custom_print("Dati inseriti con successo nella tabella 'datistorici_positioning'")
	except:
		custom_print(f"Errore durante l'inserimento dei dati sul positioning: {e}")

# Funzione per inserire i dati nella tabella bs02
def insert_data_bs02(conn, data_dict):
    try:
        sql_insert = "INSERT INTO datistorici_bs02 (mac, timestamp, h, t, l, c) VALUES (?, ?, ?, ?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None), 
            data_dict.get("timestamp", None), 
            data_dict.get("h", None), 
            data_dict.get("t", None), 
            data_dict.get("l", None),
            data_dict.get("c", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'datistorici_bs02'")
    except sqlite3.IntegrityError:
        custom_print("Errore: Duplicato trovato per (mac, timestamp). Dati non inseriti.")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati bs02: {e}")

# Funzione per inserire i dati nella tabella bangle
def insert_data_bangle(conn, data_dict):
    try:
        sql_insert = "INSERT INTO datistorici_bangle (mac, timestamp, bpm, min, max, l, c, t, p, a, s, nr, mad, v, b, rs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        cur = conn.cursor()
        cur.execute(sql_insert, (
            data_dict.get("mac", None), 
            data_dict.get("rts", None), 
            data_dict.get("BPM", None), 
            data_dict.get("m", None), 
            data_dict.get("M", None),
            data_dict.get("l", None),
            data_dict.get("c", None),
            data_dict.get("t", None),
            data_dict.get("p", None),
            data_dict.get("a", None),
            data_dict.get("s", None),
            data_dict.get("nr", None),
            data_dict.get("mad", None),
            data_dict.get("v", None),
            data_dict.get("b", None),
            data_dict.get("rs", None)
        ))
        conn.commit()
        custom_print("Dati inseriti con successo nella tabella 'datistorici_bangle'")
    except sqlite3.IntegrityError:
        custom_print("Errore: Duplicato trovato per (mac, timestamp). Dati non inseriti.")
    except sqlite3.Error as e:
        custom_print(f"Errore durante l'inserimento dei dati bangle: {e}")

with open(config_filename) as f: 
	config_data = json.load(f)
	userid = config_data['user_id']
	print (f"userid: {config_data}")
	if(userid != ""): print(f">> Modalità BS02 - ID utente: {userid}")
	else: print(f">> Modalità Bangles")

def custom_print(message_to_print):
	current_time = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
	finalMessage = f"{current_time} {message_to_print}"
	print(finalMessage)
	sys.stdout.flush()

def get_org_id():
	with open(config_filename, 'r') as f: 
		config_data = json.load(f)
		return config_data['organization_id']

def find_full_mac(last_four):
    # Aprire il file JSON e caricare i dati
	with open(config_filename, 'r') as f:
		data = json.load(f)
    
    # Elenco di dispositivi nel file JSON
	devices = data.get('devices', [])
    
    # Cerca tra i dispositivi quello con i corrispondenti ultimi 4 caratteri del MAC
	for device in devices:
		mac = device.get('mac', '')
		if mac.lower()[-5:] == last_four.lower():
			return mac  # Restituisce il MAC completo se trovato

	return None  # Restituisce None se non trova corrispondenze
	
def get_user_id(bangle_mac='dummy'):
	with open(config_filename) as f: 
		config_data = json.load(f)
		user_id = config_data['user_id']
		if(user_id != ""): return str(user_id)
		else:
			devices = config_data.get("devices", [])
			for device in devices:
				if device['mac'] == bangle_mac and device['type'] == 'banglejs2':
					return str(device['user_id'])
			custom_print('No bangle found with MAC - treating as bs02 data ' + bangle_mac)
			return "0"

async def set_global_user_id(new_user_id):
	async with aiofiles.open(config_filename, mode="r+") as f:
		config = json.loads(await f.read())
		config["user_id"] = new_user_id
		await f.seek(0)
		await f.write(json.dumps(config, indent=4))
		await f.truncate()

async def save_devices_to_json(data):
	async with aiofiles.open(config_filename, mode="r+") as f:
		config = json.loads(await f.read())
		config["devices"] = data
		await f.seek(0)
		await f.write(json.dumps(config, indent=4))
		await f.truncate()

async def load_data_from_json():
	try:
		async with aiofiles.open(config_filename, mode='r') as config:
			loaded_data = json.loads(await config.read())
			return loaded_data
	except FileNotFoundError:
		return []
	except Exception as e:
		custom_print(e)
		return []

def data_ora_corrente():
	ora_corrente = datetime.datetime.now()
	data_corrente = ora_corrente.strftime("%d-%m-%Y")
	ora_corrente = ora_corrente.strftime("%H:%M:%S")
	return data_corrente + " " + ora_corrente

async def coap_multicast_ip():
	ipv6_wpan0_clean = ipv6_wpan0.replace('%wpan0', '')
	request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=ipv6_wpan0_clean.encode(), uri='coap://[ff03::1%wpan0]/brip')
	try:
		context.request(request)
	except Exception as e:
		custom_print('Failed to fetch resource:')
		custom_print(e)

async def coap_brssi(devices):
	if(calibrating): return
	ipv6_wpan0_clean = ipv6_wpan0.replace('%wpan0', '')
	devices_with_empty_ipv6 = [device for device in devices if device.get('ipv6') == "" and device.get('type') == "bs02" and device.get('status') == True]
	custom_print("BR ipv6: " + ipv6_wpan0_clean)
 
	try:
		if len(devices_with_empty_ipv6) == 0:
			for device in devices:
				if device['type'] == 'bs02' and device['status'] == True:
					bs02_ip = device.get('ipv6', '')
					bs02_mc = device.get('mac', '')
					custom_print('unicasting to ' + bs02_ip + ' ('+bs02_mc+')')
					try:
						request = aiocoap.Message(mtype=aiocoap.CON, code=aiocoap.PUT, payload=ipv6_wpan0_clean.encode(), uri='coap://['+bs02_ip+'%wpan0]/banglerssi')
						context.request(request)
					except Exception as e:
						custom_print('Failed unicast to ' + bs02_ip + ' ('+bs02_mc+')')
						custom_print(e)
		else:
			request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=ipv6_wpan0_clean.encode(), uri='coap://[ff03::1%wpan0]/banglerssi')
			context.request(request)
  
	except Exception as e:
		custom_print('Failed to fetch resource:')
		custom_print(e)


async def coap_light(cmd, devices): # bs02 LED on = scan sensors, bangle macs
	custom_print("---- coap_light ")
	try:
		str_to_send = str(cmd)
		for device in devices:
			if device['type'] == 'banglejs2':
				str_to_send += ',' + device['mac']
		
		if str_to_send[-1] == ',':
			str_to_send = str_to_send[:-1]
   
		str_to_send += '.'
		for device in devices:
			if device['type'] == 'puckjs2':
				str_to_send += device['mac'] + ','
    
		if str_to_send[-1] == ',':
			str_to_send = str_to_send[:-1]
   
		custom_print(str_to_send)
  
		request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=str_to_send.encode(), uri='coap://[ff03::1%wpan0]/light')
		context.request(request)
	except Exception as e:
		custom_print('Failed to fetch resource:')
		custom_print(e)

class AlarmResource(resource.Resource):
	"""this resource support the PUT method"""
	
	def __init__(self):
		super().__init__()
		# self.state = "OFF"

	async def render_put(self, request):
		ausgabe = request.payload.decode('ascii')
		try:
			data = json.loads(ausgabe)
		except ValueError:
			custom_print("ERRORE NEL CONVERTIRE JSON RICEVUTO " + ausgabe)
			# await move_files_out_of_backup()
			data = ausgabe
		# print(data)
		# salvo tutti i dati in ricezione da un dispositivo dentro ad un dizionario che verrò gestito successivamente
		macAdd = data["mac"].split()[0]
		user_id = get_user_id(macAdd)
  
		# carico dati inizio connessione per device O2Ring/PC-60FW
		if macAdd not in dizionario_globale_timestamp and (data["type"] == 1 or data["type"] == 2 or data["type"] == 0 or data["type"] == 5 or data["type"] == 6 or data["type"] == 7):
			custom_print("Mac " + macAdd + " not in dizionario_globale_timestamp, adding it for live graph device...")
			dizionario_globale_timestamp[macAdd] = {
				"timestampInizio": str(round(datetime.datetime.now().timestamp())),
				"timestamp": str(round(datetime.datetime.now().timestamp())),
				"timestampFine": None,
				"type": data["type"],
				"mac": macAdd
			}
			# carico dati su db livedatabangle
			insert_data_livedatabangle(conn, dizionario_globale_timestamp[macAdd])
  
		if data["status"] == "c":
			custom_print('>Receivd: %s' % data)
    
			try:
				dizionario_globale[macAdd].append(data)
			except KeyError:
				dizionario_globale[macAdd] = []
				dizionario_globale[macAdd].append(data)
			data_realtime = {}
			# scrivo i dati in real time per O2Ring e PC-60FW
			if data["type"] == 1 or data["type"] == 2:
				data_realtime = {
					'hr': data['BPM'],
					'spO2': data['Ossigeno'],
     				'timestamp': int(datetime.datetime.now().timestamp() * 1_000_000)
				}
				# write_data_to_firebase_realtime(
				# 	data_realtime, str(user_id) + "/liveMisuration/oximeter")
			# scrivo i dati in real time per BP2
			if data["type"] == 0:
				data_realtime = {
					'hr': data['BPM'],
					'DIA': data['DIA'],
					'SYS': data['SYS'],
				}
				# write_data_to_firebase_realtime(
				# 	data_realtime, str(user_id) + "/liveMisuration/sphygmomanometer")
			# GESTISCO UPLOAD DEI DATI PER BANGLEJS2
			if data["type"] == 6:
				print("> Dati Bangle Arrivati")
				# mando dati per scrittura su db lite
				insert_data_bangle(conn, data)
				result_data_file = {}
				for k in data.keys():
					result_data_file[k] = data[k]

				# Gestione speciale per 'rts' se presente e valido, per calcolare il timestamp
				if 'rts' in data and data['rts'] is not None:
					result_data_file['timestamp'] = str(int(datetime.datetime.fromtimestamp(
						int(data['rts']),
						pytz.timezone('UTC')
					).astimezone(pytz.timezone('Europe/Rome')).timestamp()))
     
				if os.path.exists(config_filename):
					with open(config_filename, 'r') as file:
						config = json.load(file)
					# Passo 2 e 3: Trova il dispositivo e aggiorna il valore di versione
					device_found = False
					for device in config.get("devices", []):
						if device.get("mac") == macAdd and device.get("type") == "banglejs2":
							device["v"] = str(data['v'])
							device_found = True
							break

					if not device_found:
						custom_print(f"Dispositivo con MAC {macAdd} non trovato nel file config.json")
					else:
						# Passo 4: Scrivi la configurazione aggiornata nel file
						with open(config_filename, 'w') as file:
							json.dump(config, file, indent=4)
						custom_print("Configurazione in config.json aggiornata con successo.")
				else:
					custom_print("Il file config.json non esiste o non è stato trovato")

				data_formattata = datetime.date.today().strftime("%d-%m-%Y")
    
				# Converti il timestamp UNIX (secondi dall'epoca) in un oggetto datetime
				timestamp = int(data['rts'])
				ora_italiana = datetime.datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Rome'))

				# Arrotonda l'ora per rimuovere minuti, secondi e microsecondi
				ora_italiana = ora_italiana.replace(minute=0, second=0, microsecond=0)

				# Converti il timestamp UNIX in un oggetto datetime in UTC
				ora_utc = datetime.datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc)

				# carico dati battiti bangle
				# if "BPM" in data:
					# try:
					# 	# provo ad aggiornare un file già presente per battiti						
					# 	firestore_db.collection("biometricData/"+str(user_id)+"/watchDevices/hourly/heartRate").document(data_formattata).update(
					# 		{
					# 			str(ora_italiana.time().hour).zfill(2) + ":00":
					# 			{
					# 				"avgHR": float(data["BPM"]),
					# 				"count": float(data["nr"]),
					# 				"maxHR": float(data["M"]),
					# 				"minHR": float(data["m"]),
					# 				"timestamp": ora_utc,
					# 			},
					# 			"timestamp": ora_utc.replace(hour=0, minute=0, second=0, microsecond=0),
					# 		})
					# except:
					# 	# se non trovato lo creo
					# 	firestore_db.collection("biometricData/"+str(user_id)+"/watchDevices/hourly/heartRate").document(data_formattata).set(
					# 		{
					# 			str(ora_italiana.time().hour).zfill(2) + ":00":
					# 			{
					# 				"avgHR": float(data["BPM"]),
					# 				"count": float(data["nr"]),
					# 				"maxHR": float(data["M"]),
					# 				"minHR": float(data["m"]),
					# 				"timestamp": ora_utc,
					# 			},
					# 			"timestamp": ora_utc.replace(hour=0, minute=0, second=0, microsecond=0),
					# 		})
					# carico dati passi bangle
					# try:
					# 	# provo ad aggiornare un file già presente per battiti						
					# 	firestore_db.collection("biometricData/"+str(user_id)+"/watchDevices/hourly/steps").document(data_formattata).update(
					# 		{
					# 			str(ora_italiana.time().hour).zfill(2) + ":00":
					# 			{
					# 				"valueSteps": data["s"],
					# 				"timestamp": ora_utc,
					# 			},
					# 			"timestamp": ora_utc.replace(hour=0, minute=0, second=0, microsecond=0),
					# 		})
					# except:
					# 	# se non trovato lo creo
					# 	firestore_db.collection("biometricData/"+str(user_id)+"/watchDevices/hourly/steps").document(data_formattata).set(
					# 		{
					# 			str(ora_italiana.time().hour).zfill(2) + ":00":
					# 			{
					# 				"minHR": data["s"],
					# 				"timestamp": ora_utc,
					# 			},
					# 			"timestamp": ora_utc.replace(hour=0, minute=0, second=0, microsecond=0),
					# 		})
		
					# Aggiornamento dei lastValues
					# firestore_db.collection("biometricData").document(str(user_id)).update({
					# 	"lastValues.hr.last": data["BPM"],
					# 	"lastValues.hr.timestamp": ora_utc,
					# 	"lastValues.steps.timestamp": ora_utc,
					# 	# to do: step divisi per ora
					# })
				# else:
				# 	print("BPM does not exist.")

		if data["status"] == "d":
			# if(str(user_id) != ''): delete_data_from_firebase_realtime(str(user_id) + "/liveMisuration")
			macAdd = data["mac"].split()[0]
			custom_print(data)
			
   			# carico dati di disconnessione live connection su db 
			if macAdd in dizionario_globale_timestamp:
				custom_print("Mac " + macAdd + " not in dizionario_globale_timestamp, adding it for live graph device...")
				dizionario_globale_timestamp[macAdd] = {
					"timestampFine": str(round(datetime.datetime.now().timestamp())),
					"timestamp": str(round(datetime.datetime.now().timestamp())),
					"timestampInizio": None,
					"type": data["type"],
					"mac": macAdd
				}
				# carico dati su db livedatabangle
				insert_data_livedatabangle(conn, dizionario_globale_timestamp[macAdd])
				del dizionario_globale_timestamp[macAdd]
   
			if macAdd in dizionario_globale:
				custom_print("******************************************")
				custom_print(data_ora_corrente())
				custom_print("Uploading data to Cloud from " + macAdd)
				custom_print("******************************************")
				# gestione date
				oggi = datetime.date.today()
				data_formattata = oggi.strftime("%d-%m-%Y")
				data_corrente = datetime.date.today()
				orario_inizio_giornata = datetime.datetime.combine(
					data_corrente, datetime.time.min)
				microsecondi_epoch = int(
					orario_inizio_giornata.timestamp() * 1_000_000)

				# GESTISCO UPLOAD DEI DATI PER BP2 e BP2A (sfigmomanometro)
				# if data["type"] == 0:
				# 	try:
				# 		# provo ad aggiornare un file già presente per battiti
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/bloodPressure").document(data_formattata).update(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.now().time().hour).zfill(2) + ":00":
				# 				{
				# 				"DIA": dizionario_globale[macAdd][0]["BPM"], 
				# 				"SYS": dizionario_globale[macAdd][0]["SYS"], 
				# 				"timestamp": datetime.datetime.now(),
				# 				},
				# 				"timestamp": datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
      
				# 		# Aggiornamento del valore hr e del timestamp all'interno della mappa lastValues
				# 		firestore_db.collection("biometricData").document(str(user_id)).update({
				# 			"lastValues.bloodPressure.DIA": dizionario_globale[macAdd][0]["BPM"],
       			# 			"lastValues.bloodPressure.SYS": dizionario_globale[macAdd][0]["SYS"],
				# 			"lastValues.bloodPressure.timestamp": datetime.datetime.now()
				# 		})
				# 	except:
				# 		# se non trovato lo creo
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/bloodPressure").document(data_formattata).set(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.now().time().hour).zfill(2) + ":00":
				# 				{
				# 				"DIA": dizionario_globale[macAdd][0]["BPM"], 
				# 				"SYS": dizionario_globale[macAdd][0]["SYS"], 
				# 				"timestamp": datetime.datetime.now(),
				# 				},
				# 				"timestamp": datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
      
			

				# GESTISCO UPLOAD DEI DATI PER O2RING e PC-60FW (ossimetri)
				# if data["type"] == 1 or data["type"] == 2:
				# 	lista_dati_fb_bpm = []
				# 	lista_dati_fb_oxy = []
					
				# 	try:
				# 		for elemento in dizionario_globale[macAdd]:
				# 			lista_dati_fb_bpm.append(elemento['BPM'])
				# 			lista_dati_fb_oxy.append(elemento['Ossigeno'])
				# 	except:
				# 		print("fine comunicazione")
				# 	try:
				# 		# provo ad aggiornare un file già presente per battiti
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/heartRate").document(data_formattata).update(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.now().time().hour).zfill(2) + ":00":
				# 				{
				# 				"minHR": min(lista_dati_fb_bpm), 
				# 				"avgHR": round(sum(lista_dati_fb_bpm) / len(lista_dati_fb_bpm), 2), 
				# 				"maxHR": max(lista_dati_fb_bpm), 
				# 				"count": len(lista_dati_fb_bpm), 
				# 				"sumHR": sum(lista_dati_fb_bpm),
				# 				"timestamp": datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0),
				# 				},
				# 				"timestamp": datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
      
				# 		# Aggiornamento del valore hr e del timestamp all'interno della mappa lastValues
				# 		firestore_db.collection("biometricData").document(str(user_id)).update({
				# 			"lastValues.hr.last": round(sum(lista_dati_fb_bpm) / len(lista_dati_fb_bpm), 2),
				# 			"lastValues.hr.timestamp": datetime.datetime.utcnow()
				# 		})
				# 	except:
				# 		# se non trovato lo creo
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/heartRate").document(data_formattata).set(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.utcnow().time().hour).zfill(2)+":00": 
				# 				{
				# 				"minHR": min(lista_dati_fb_bpm), 
				# 				"avgHR": round(sum(lista_dati_fb_bpm) / len(lista_dati_fb_bpm), 2), 
				# 				"maxHR": max(lista_dati_fb_bpm), 
				# 				"count": len(lista_dati_fb_bpm), 
				# 				"sumHR": sum(lista_dati_fb_bpm),
				# 				"timestamp": datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
				# 				},
				# 				"timestamp": datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
					
				# 	try:
				# 		# provo ad aggiornare un file già presente per ossigeno
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/spO2").document(data_formattata).update(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.utcnow().time().hour).zfill(2)+":00": 
				# 				{
				# 				"minspO2": min(lista_dati_fb_oxy), 
				# 				"avgspO2": round(sum(lista_dati_fb_oxy) / len(lista_dati_fb_oxy), 2), 
				# 				"maxspO2": max(lista_dati_fb_oxy), 
				# 				"count": len(lista_dati_fb_oxy),
				# 				"sumspO2": sum(lista_dati_fb_bpm), 
				# 				"timestamp": datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
				# 				},
				# 				"timestamp": datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
				# 		# Update the lastValue field in the collection
						
				# 		# Aggiornamento del solo valore spO2 all'interno della mappa lastValues
				# 		firestore_db.collection("biometricData").document(str(user_id)).update({
				# 			"lastValues.spO2.last": round(sum(lista_dati_fb_oxy) / len(lista_dati_fb_oxy), 2),
				# 			"lastValues.spO2.timestamp": datetime.datetime.utcnow()
				# 		})
						
				# 	except:
				# 		# se non trovato lo creo
				# 		firestore_db.collection("biometricData/"+str(user_id)+"/bleDevices/hourly/spO2").document(data_formattata).set(
				# 			{"idUtente": str(user_id), 
				# 				str(datetime.datetime.now().time().hour).zfill(2)+":00": 
				# 				{
				# 				"minspO2": min(lista_dati_fb_oxy), 
				# 				"avgspO2": round(sum(lista_dati_fb_oxy) / len(lista_dati_fb_oxy), 2), 
				# 				"maxspO2": max(lista_dati_fb_oxy), 
				# 				"count": len(lista_dati_fb_oxy),
				# 				"sumspO2": sum(lista_dati_fb_bpm), 
				# 				"timestamp": datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
				# 				},
				# 				"timestamp": datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
				# 			})
					
				# GESTISCO UPLOAD DEI DATI PER I THINGY
				# if data["type"] == 3:
				# 	diz_temp = {}
				# 	for i in dizionario_globale[macAdd]:
				# 		if 'T' in i:
				# 			misura = 'T'
				# 			diz_temp['T'] = i['T']
				# 		if 'H' in i:
				# 			misura = 'H'
				# 			diz_temp['H'] = i['H']
				# 		if 'P' in i:
				# 			misura = 'P'
				# 			diz_temp['P'] = i['P']
				# 		if 'G' in i:
				# 			misura = 'G'
				# 			diz_temp['G'] = i['G']
				# 		diz_temp['timestamp'] = int(
				# 			datetime.datetime.now().timestamp() * 1_000_000)
				# 	try:
				# 		# provo ad aggiornare un file già presente per la pressione del paziente
				# 		firestore_db.collection("allDeviceRecordSensoriAria").document(user_id+i["mac"]+data_formattata).update(
				# 			{"idUtente": user_id, "lastUpdate": int(datetime.datetime.now().timestamp() * 1_000_000), "timestampGiornata": microsecondi_epoch, "location": i["zone"], "mac": i["mac"], str(diz_temp['timestamp']): diz_temp})
				# 	except:
				# 		# se non trovato lo creo
				# 		firestore_db.collection("allDeviceRecordSensoriAria").document(user_id+i["mac"]+data_formattata).set(
				# 			{"idUtente": user_id, "lastUpdate": int(datetime.datetime.now().timestamp() * 1_000_000), "timestampGiornata": microsecondi_epoch, "location": i["zone"], "mac": i["mac"], str(diz_temp['timestamp']): diz_temp})


				# GESTISCO UPLOAD DEI DATI PER BS02 
				# if data["type"] == 4:
				# 	# ******************************************************************
				# 	# PREPARO JSON CONTENENTE DATI BS02 E LO SCRIVO SU FILE LOCALE NEL BR
				# 	result_data = {'version': data['v'], 'level': data['l'], 'temp': data['t'], 'hum': data['h'], 'mac': data['mac'].split()[0].replace('(', ''), 'timestamp': int(datetime.datetime.now().timestamp() * 1_000_000)}
				# 	result_data_file = {'c': str(data['c']), 'l': str(data['l']), 't': str(data['t']), 'h': str(data['h']), 'mac': data['mac'].split()[0].replace('(', ''), 'timestamp': str(round(datetime.datetime.now().timestamp()))}
				# 	await update_ipv6_address(data['mac'].split()[0].replace('(', ''), data['IP'])

				# 	if data['mac'].split()[0].replace('(', '') not in ipv6logs or ipv6logs[data['mac'].split()[0].replace('(', '')] != data['IP']:
				# 		ipv6logs[data['mac'].split()[0].replace('(', '')] = data['IP']
				# 		insert_data_logdevices(conn, {
				# 			"mac": data['mac'].split()[0].replace('(', ''),
				# 			"type": data['IP'],
				# 			"timestamp": str(round(datetime.datetime.now().timestamp()))
				# 		})
				# 	# print("******ipv6logs*******")
				# 	# print(ipv6logs)
				# 	# print("*********************")	

				# 	# salvataggio dati db lite
				# 	insert_data_bs02(conn, result_data_file)
					
				# 	# AGGIORNO LE VERSIONE DEI BS02
				# 	# Passo 1: Leggi il file config.json
				# 	if os.path.exists(config_filename):
				# 		with open(config_filename, 'r') as file:
				# 			config = json.load(file)
				# 		# Passo 2 e 3: Trova il dispositivo e aggiorna il valore di versione
				# 		device_found = False
				# 		for device in config.get("devices", []):
				# 			if device.get("mac") == macAdd and device.get("type") == "bs02":
				# 				device["v"] = str(data['v'])
				# 				device_found = True
				# 				break

				# 		if not device_found:
				# 			print(f"Dispositivo con MAC {macAdd} non trovato nel file config.json")
				# 		else:
				# 			# Passo 4: Scrivi la configurazione aggiornata nel file
				# 			with open(config_filename, 'w') as file:
				# 				json.dump(config, file, indent=4)
				# 			print("Configurazione in config.json aggiornata con successo.")
				# 	else:
				# 		print("Il file config.json non esiste o non è stato trovato")

				# 	# SCRITTURA SU FB DEI DATI DEL BS02
				# 	organization_id = get_org_id()
     
				# 	# Costruisce il path al documento
				# 	base_path = "organization/" + str(organization_id)

				# 	# Prova prima con "network"
				# 	doc_path2 = f"{base_path}/network/{eth0_mac.lower()}/bs02/{result_data['mac']}"
				# 	doc_ref = firestore_db.document(doc_path2)
					
				# 	try:
				# 		doc = doc_ref.get()
				# 		if doc.exists:
				# 			# Il documento esiste, aggiorna
				# 			path_to_use = doc_path2
				# 		else:
				# 			# Prova con "nursery" se "network" non esiste
				# 			doc_path2 = f"{base_path}/nursery/{eth0_mac.lower()}/bs02/{result_data['mac']}"
				# 			doc_ref = firestore_db.document(doc_path2)
				# 			doc = doc_ref.get()
				# 			if doc.exists:
				# 				path_to_use = doc_path2
				# 			else:
				# 				# Se neanche "nursery" esiste, scegli uno dei due percorsi per creare il documento
				# 				path_to_use = doc_path2  # O scegliere esplicitamente '/network/' se preferisci
						
				# 		# Update the document with the new data
				# 		firestore_db.document(path_to_use).update({
				# 			"lastValues": {
				# 				"version": result_data['version'],
				# 				"level": result_data['level'],
				# 				"temp": result_data['temp'],
				# 				"hum": result_data['hum'],
				# 				"timestamp": datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
				# 			}
				# 		})
				# 		custom_print("Dati BS02 su fb salvati correttamente")

				# 	except Exception as e:
				# 		print(f"Si è verificato un errore durante il salvataggio dei dati bs02 su FB: {e}")
      
					
				# GESTISCO UPLOAD DEI DATI PER BILANCIA 
				# if data["type"] == 5:
				# 	# dati per orario
				# 	data_odierna = datetime.datetime.now()
				# 	mezzanotte = datetime.datetime(data_odierna.year, data_odierna.month, data_odierna.day)
				# 	timestamp_mezzanotte = mezzanotte.timestamp()
				# 	#
				# 	ora_formattata = datetime.datetime.now().strftime("%H:%M")
				# 	document_path = f"biometricData/{user_id}/bleDevices/hourly/weight/{data_formattata}"
				# 	document_data = {
				# 		"idUtente": user_id,
				# 		"timestamp": datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
				# 		ora_formattata: {
				# 			"weight": float(data["pesoKg"]),
				# 			"timestamp": datetime.datetime.now().replace(minute=0, second=0, microsecond=0),
				# 		}
				# 	}
     
				# 	# Aggiornamento del valore hr e del timestamp all'interno della mappa lastValues
				# 	firestore_db.collection("biometricData").document(str(user_id)).update({
				# 		"lastValues.weight.last": float(data["pesoKg"]),
				# 		"lastValues.weight.timestamp": datetime.datetime.now()
				# 	})

				# 	try:
				# 		# Prova ad aggiornare il documento
				# 		firestore_db.collection("biometricData").document(user_id).collection("bleDevices").document("hourly").collection("weight").document(data_formattata).update({
				# 			ora_formattata: document_data[ora_formattata],
				# 			"idUtente": document_data["idUtente"],
				# 			"timestamp": document_data["timestamp"]
				# 		})
				# 		print("Dati sul peso aggiornati con successo.")
				# 	except Exception as e:
				# 		# Gestisci l'eccezione come necessario
				# 		firestore_db.collection("biometricData").document(user_id).collection("bleDevices").document("hourly").collection("weight").document(data_formattata).set({
				# 			ora_formattata: document_data[ora_formattata],
				# 			"idUtente": document_data["idUtente"],
				# 			"timestamp": document_data["timestamp"]
				# 		})
				# 		print("Dati sul peso creati con successo.")
				
				del dizionario_globale[macAdd]
		return aiocoap.Message(code=aiocoap.CHANGED, payload="")

class NodeIp(resource.Resource):
	"""this resource support the PUT method"""

	def __init__(self):
		super().__init__()

	async def render_put(self, request):
		ausgabe = request.payload.decode('ascii')
		try:
			data = json.loads(ausgabe)
		except ValueError:
			custom_print("ERRORE NEL CONVERTIRE JSON RICEVUTO " + ausgabe)
			data = ausgabe
		mac_add = data["mac"].split()[0]
		ip_add = data["IP"].split()[0]

		data = await load_data_from_json()
		devices = data.get("devices", [])
		for device in devices:
			if device["mac"] == mac_add:
				device["ipv6"] = ip_add
				break
		await save_devices_to_json(devices)
		return aiocoap.Message(code=aiocoap.CHANGED, payload="")

class StorebRssi(resource.Resource):
    """Resource to handle PUT requests for RSSI data from bs02 devices."""

    def __init__(self):
        super().__init__()
        self.config_data = self.load_config()

    def load_config(self):
        """Load configuration data from a JSON file."""
        if os.path.exists(config_filename):
            with open(config_filename, 'r') as file:
                return json.load(file)
        else:
            raise FileNotFoundError("Configuration file not found")

    async def render_put(self, request):
        """Handle PUT requests with RSSI data."""
        ausgabe = request.payload.decode('utf-8')
        try:
            data = json.loads(ausgabe)
            print("Received RSSI:", data)
            await self.save_to_db(data)
            await self.process_and_save_data(data)
        except ValueError:
            print("Error converting received JSON:", ausgabe)
        return aiocoap.Message(code=aiocoap.CHANGED, payload="Data processed".encode('utf-8'))

    async def process_and_save_data(self, data):
        """Map full MAC addresses for bs02 and save data to a JSON file."""
        file_path = start_path+'/shared_dir/bangle_position_temp.json'

        # Load existing data if the file exists
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                existing_data = json.load(file)
        else:
            existing_data = {}

        for partial_mac_bs02, rssi_values in data.items():
            full_mac_bs02 = self.find_full_mac(partial_mac_bs02)
            for i in range(0, len(rssi_values), 2):
                partial_mac_bangle, rssi = rssi_values[i], rssi_values[i+1]
                full_mac_bangle = self.find_full_mac(partial_mac_bangle)
                if full_mac_bangle not in existing_data:
                    existing_data[full_mac_bangle] = {'mac_device': full_mac_bangle}
                existing_data[full_mac_bangle][full_mac_bs02] = rssi  # Update with new RSSI value

        # Save updated data to the file
        with open(file_path, 'w') as file:
            json.dump(existing_data, file, indent=4)
            print("Data saved to", file_path)

    def find_full_mac(self, partial_mac):
        """Match the partial MAC address to a complete MAC address from the configuration."""
        for device in self.config_data.get('devices', []):
            if device['mac'].endswith(partial_mac):
                return device['mac']
        return "Unknown MAC"

    # funzione per scrivere storici
    async def save_to_db(self, data):
        global cleaning_data_flag
        global conn

        entries = []

        # Si assume che la chiave del dizionario sia il MAC del BS02
        for key, value in data.items():
            mac_bs02 = key
            # Iterazione sull'array in coppie di MAC Bangle e RSSI
            for i in range(0, len(value), 2):
                mac_bangle = value[i]
                rssi = value[i + 1]
                entry = {
                    "timestamp": str(round(datetime.datetime.now().timestamp())),
                    "macBs02": self.find_full_mac(mac_bs02),
                    "macBangle": self.find_full_mac(mac_bangle),
                    "rssiBangle": str(-abs(rssi))  # Converti RSSI in negativo e poi in stringa
                }
                entries.append(entry)

        # scrivo dati sul db
        insert_data_positioning(conn, entries)

class BangleAlarm(resource.Resource):
	"""this resource support the PUT method"""

	def __init__(self):
		super().__init__()

	async def render_put(self, request):
		global diceface
		ausgabe = request.payload.decode('ascii')
		try:
			data = json.loads(ausgabe)
			
			if "cmd" not in data:
				custom_print("ALARM: " + str(data))

				# carico dati su db livedatabangle
				insert_data_livedatabangle(conn, {
					"timestampInizio": str(round(datetime.datetime.now().timestamp())),
					"timestamp": str(round(datetime.datetime.now().timestamp())),
					"timestampFine": None,
					"type": 99,
					"mac": str(data["mac"])
				})

			else:
				custom_print("DICE COMMUNICATION: " + str(data))
				custom_print("Dizionario diceface :" + str(diceface))
				if str(data["mac"]) in diceface and diceface[str(data["mac"])] != str(data["cmd"]):
					custom_print("FACE CHANGED FOR DICE : " + str(data["mac"]))
					diceface[str(data["mac"])] = str(data["cmd"])
					insert_data_diceface(conn, {
						"face": str(data["cmd"]),
						"timestamp": str(round(datetime.datetime.now().timestamp())),
						"mac": str(data["mac"])
					})
				elif str(data["mac"]) not in diceface:
					custom_print("NEW DICE DETECTED : " + str(data["mac"]))
					diceface[str(data["mac"])] = str(data["cmd"])
					insert_data_diceface(conn, {
						"face": str(data["cmd"]),
						"timestamp": str(round(datetime.datetime.now().timestamp())),
						"mac": str(data["mac"])
					})
				else:
					custom_print("NOTHING TO DO WITH THIS INFORMATION")
    
		except ValueError:
			custom_print("ERRORE NEL CONVERTIRE JSON RICEVUTO " + ausgabe)
			data = ausgabe
		#mac_bs02 = data["mac"].split()[0]
		return aiocoap.Message(code=aiocoap.CHANGED, payload="")

class BangleTime(resource.Resource):
	"""this resource support the PUT method"""

	def __init__(self):
		super().__init__()

	async def render_put(self, request):
		local_timezone = tzlocal.get_localzone()
		current_epoch = int(time.time())
		current_datetime = datetime.datetime.now(local_timezone)
		timezone_offset = current_datetime.utcoffset().total_seconds()
		timestamp_with_offset = current_epoch + int(timezone_offset)
		timestamp_str = str(timestamp_with_offset)
		bytes_to_send = bytes(timestamp_str, 'utf-8')
		return aiocoap.Message(code=aiocoap.CHANGED, payload=bytes_to_send)

class Bs02Booted(resource.Resource):
	"""this resource support the PUT method"""

	def __init__(self):
		super().__init__()

	async def render_put(self, request):
		custom_print("BS02 LOGS: " + str(request.payload.decode('ascii')))
		parts = str(request.payload.decode('ascii')).split(',')
		insert_data_logdevices(conn, {
			"mac": parts[0],
			"type": parts[1],
			"timestamp": str(round(datetime.datetime.now().timestamp()))

		})
		return aiocoap.Message(code=aiocoap.CHANGED, payload="")

# funzione per prendere ipv6 dell'interfaccia di rete wpan0 e mac eth0
def get_ipv6_wpan0():
	interfaces = netifaces.interfaces()
 
	for i in interfaces:
		if i == 'eth0':
			global eth0_mac 
			eth0_mac = netifaces.ifaddresses(i)[netifaces.AF_LINK][0]['addr']
   
	if 'wpan0' in interfaces:
		addresses = netifaces.ifaddresses('wpan0')
		if netifaces.AF_INET6 in addresses:
			ipv6_addresses = addresses[netifaces.AF_INET6]
			if len(ipv6_addresses) > 0:
				return ipv6_addresses[1]['addr']

	return None

# Returns (incremented) current matter id
async def get_next_matter_id(do_increment: bool):
	async with aiofiles.open(config_filename, mode="r+") as f:
		content = await f.read()
		config = json.loads(content)
		if do_increment:
			config["current_matter_id"] += 1
			await f.seek(0)
			await f.write(json.dumps(config, indent=4))
			await f.truncate()
		return config["current_matter_id"]

async def send_post_request_async(endpoint, request_data):
    full_url = f"{host_url}{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.post(full_url, data=json.dumps(request_data), headers={'Content-Type': 'application/json'}) as response:
            if response.status // 100 == 2:
                custom_print(await response.text())
            else:
                custom_print(f"Error: {response.status}\n{await response.text()}")

async def get_watch_v(dev_type):
    async with aiohttp.ClientSession() as session:
        async with session.post(getlatestv_endpoint, data=json.dumps({"dev_type": dev_type}), headers={'Content-Type': 'application/json'}) as response:
            if response.status // 100 == 2:
                response_json = await response.json()
                return response_json.get("v")
            else:
                custom_print(f"Error: {response.status}\n{await response.text()}")
                return None

async def handle(req):
		if req.path == '/commission': # Configure a device
			type = req.query['type'] #  "bs02"  /  "banglejs2"  /  "puckjs2"
			mac = req.query['mac']
			name = req.query['name']
			user_id = req.query.get('user_id','') # optional, used for bangle
			location = req.query.get('location','') # optional, used for bs02
			psk = req.query.get('psk','') # optional, used for bs02, psk for secure thread commissioning
			eui64ExtId = req.query.get('eui64ExtId','') # optional, used for bs02, device identifier
			custom_print("Commissioning " + mac)
   
			try:
				if type == "bs02":
					response = requests.post(addjoiner_endpoint, json={ 'eui64ExtId': eui64ExtId, 'psk': psk }, headers={'Content-type': 'application/json'})
					if response.status_code != 200: return web.Response(status=500)
				data = await load_data_from_json()
				devices = data.get("devices", [])
				devices.append({
					"type": type,
					"mac": mac,
					"user_id": user_id,
					"ipv6": "",
					"status":True,
					"name": name,
					"location": location
				})
				await save_devices_to_json(devices)
    
				if type == "banglejs2": 
					await set_global_user_id("")
					await coap_light(0, devices)
					custom_print("Light: 0")
    
				return web.Response(text=json.dumps({}))
			except Exception as e:
				custom_print(f"Commission failed: {e}")
    
		elif req.path == "/uncommission": # Uncommission bs02 or bangle
			mac = req.query['mac']
			custom_print("Uncommissioning device...")
			with open(config_filename, "r+") as f:
				data = json.load(f)
				for i, device in enumerate(data["devices"]):
					if device["mac"] == mac:
						if(device["type"] == "bs02"):
							request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, uri='coap://['+device["ipv6"]+'%wpan0]/uncommission')
							try:
								context.request(request)
								del data["devices"][i]
								f.seek(0)
								json.dump(data, f, indent=4)
								f.truncate()
								return web.Response(status=200)
							except Exception as e:
								custom_print('Failed to fetch resource:')
								custom_print(e)
								return web.Response(status=500)
						else:
							bangle_count = 0
							for device in data["devices"]:
								if device["type"] == "banglejs2":
									bangle_count += 1
							if(bangle_count == 1):
								data["user_id"] = device["user_id"]
								await coap_light(0, data["devices"])
								custom_print("Light: 0")
							del data["devices"][i]
							f.seek(0)
							json.dump(data, f, indent=4)
							f.truncate()
							return web.Response(status=200)

		elif req.path == '/getdevice': # Return name, location, and IPv6 address of bs02
			mac = req.query['mac']
			with open(config_filename, "r") as f:
				config = json.load(f)
			for device in config["devices"]:
				if device["mac"] == mac:
					return web.Response(text=json.dumps(device))
					
		elif req.path == '/getupdates': # Return the changelog
			with open(log_filename, "r") as f:
				return web.Response(text=json.dumps(json.load(f)))

		elif req.path == '/buzz': # Activate buzzer of device: 0 Buzzer sweep   1 Buzzer 4 KHz   2 Buzzer 1000 Hz vol++
			buzz_type = req.query['type']
			mac = req.query['mac']
			with open(config_filename, "r") as f:
				config = json.load(f)
			for device in config["devices"]:
				if device["mac"] == mac:
					request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=str(buzz_type).encode(), uri='coap://[' + device["ipv6"] + '%wpan0]/buzz')
					try:
						context.request(request)
						return web.Response(status=200)
					except Exception as e:
						custom_print('Failed to fetch resource:')
						custom_print(e)
						return web.Response(status=500)
  
		elif req.path == "/setusermode": # empty string = Bangles mode  non empty = BS02 mode -> set general user_id
			user_mode = req.query.get('user_mode', '')
			custom_print("Setting user mode...")
			try:
				with open(config_filename, 'r+') as f:
					data = json.load(f)
					data['user_id'] = user_mode
					devices = data.get('devices', [])
					f.seek(0)
					json.dump(data, f, indent=4)
					f.truncate()
					bs02_mode = user_mode != "" # If general user_id is not set
					await coap_light(1 if bs02_mode else 0, devices)
					return web.Response(status=200)
			except Exception as e:
				custom_print(f"Setusermode failed: {e}")
    
		elif req.path == "/changeuserid": # Change a bangle's user_id
			bangle_mac = req.query['mac']
			user_id = req.query['user_id']
			try:
				with open(config_filename, 'r+') as f:
					data = json.load(f)
					devices = data.get("devices", [])
					for device in devices:
						if device['mac'] == bangle_mac:
							device['user_id'] = user_id
							f.seek(0)
							json.dump(data, f, indent=4)
							f.truncate()
							return web.Response(status=200)
					return web.Response(status=500)
			except Exception as e:
				custom_print(f"Setusermode bs02 failed: {e}")
    
		elif req.path == "/calibratepositioning": # Calibrate bangle & puck rssi positioning
			banglepuck_mac = req.query['mac']
			calibrate_mode = req.query.get('calibrate_mode', "0")
			CalibrateData().set_current_room(req.query.get('room', 'Unknown'))
			CalibrateData().set_current_device(banglepuck_mac)
			room = req.query.get('room', 'Unknown')  # Ricava il nome della stanza dalla query
			data = await load_data_from_json()
			devices = data.get("devices", [])
			devices_with_empty_ipv6 = [device for device in devices if device.get('ipv6') == "" and device.get('type') == "bs02" and device.get('status') == True]
			if(len(devices_with_empty_ipv6) > 0 and calibrate_mode != 0): return web.Response(status=500)
			emergency_stop = len(devices_with_empty_ipv6) > 0 and calibrate_mode == 0
			global calibrating
			calibrating = calibrate_mode == "1"
			custom_print('Set calibrating to '+ str(calibrating))
			if calibrate_mode != "2" and not emergency_stop:
				for device in devices:
					if device['type'] == 'bs02' and device['status'] == True:
						bs02_ip = device.get('ipv6', '')
						bs02_mc = device.get('mac', '')
						custom_print('unicasting calibrate to ' + bs02_ip + ' ('+bs02_mc+')')
						request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=(calibrate_mode+','+banglepuck_mac).encode(), uri='coap://['+bs02_ip+'%wpan0]/calibratepositioning')
						context.request(request)
			else:
				# Invia un segnale al file calibrate_data.py per salvare i dati
				await CalibrateData().save_calibration_data()  # Usa un payload vuoto per chiamare render_put e salvare i dati
			if emergency_stop:
				request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=(calibrate_mode+','+banglepuck_mac).encode(), uri='coap://[ff03::1%wpan0]/calibratepositioning')
				try:
					context.request(request)
				except Exception as e:
					custom_print('Failed to fetch resource:')
					custom_print(e)
			
			return web.Response(status=200)

		elif req.path == "/editpositioning": # Edit positioning data
			banglepuck_mac = req.query['mac']
			calibrate_mode = req.query.get('calibrate_mode', "0")
			room = req.query.get('room', 'Unknown')  # Ricava il nome della stanza dalla query
			
			CalibrateData().set_current_room(room)
			CalibrateData().set_current_device(banglepuck_mac)

			data = await load_data_from_json()
			devices = data.get("devices", [])
			devices_with_empty_ipv6 = [device for device in devices if device.get('ipv6') == "" and device.get('type') == "bs02" and device.get('status') == True]

			if len(devices_with_empty_ipv6) > 0 and calibrate_mode != "0":
				return web.Response(status=500)
			emergency_stop = len(devices_with_empty_ipv6) > 0 and calibrate_mode == "0"
			
			calibrating = calibrate_mode == "1"
			custom_print('Set calibrating to ' + str(calibrating))

			if calibrate_mode == "1":
				await CalibrateData().load_calibration_data()
				CalibrateData().remove_room_data(room)

			if calibrate_mode != "2" and not emergency_stop:
				for device in devices:
					if device['type'] == 'bs02' and device['status'] == True:
						bs02_ip = device.get('ipv6', '')
						bs02_mc = device.get('mac', '')
						custom_print('unicasting calibrate to ' + bs02_ip + ' (' + bs02_mc + ')')
						request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=(calibrate_mode + ',' + banglepuck_mac).encode(), uri='coap://[' + bs02_ip + '%wpan0]/calibratepositioning')
						context.request(request)
			else:
				# Invia un segnale al file calibrate_data.py per salvare i dati
				await CalibrateData().save_calibration_data()  # Usa un payload vuoto per chiamare render_put e salvare i dati

			if emergency_stop:
				request = aiocoap.Message(mtype=aiocoap.NON, code=aiocoap.PUT, payload=(calibrate_mode + ',' + banglepuck_mac).encode(), uri='coap://[ff03::1%wpan0]/calibratepositioning')
				try:
					context.request(request)
				except Exception as e:
					custom_print('Failed to fetch resource:')
					custom_print(e)

			return web.Response(status=200)

		elif req.path == "/slowcalibration":
			banglepuck_mac = req.query['mac']
			timestampInizio = req.query['timestamp_inizio']
			timestampFine = req.query['timestamp_fine']
			room = req.query.get('room_id', 'Unknown')
	
			print(await CalibrateData().slow_calibration(banglepuck_mac, timestampInizio, timestampFine, room))
			return web.Response(status=200)

		else:
			return web.Response(status=404)

async def copy_file_after_delay(temp_file, final_file, delay):
    await asyncio.sleep(delay)
    if os.path.exists(temp_file):
        shutil.copy(temp_file, final_file)
        print(f"Copied {temp_file} to {final_file}")

async def multicast_brssi_periodically():
    first_run = True

    # Elimina i file se esistono all'inizio
    temp_file = start_path+'/shared_dir/bangle_position_temp.json'
    final_file = start_path+'/shared_dir/bangle_position.json'
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(final_file):
        os.remove(final_file)

    while True:
        if not is_updating and not calibrating:
            data = await load_data_from_json()
            devices = data.get("devices", [])
            user_id = data['user_id']
            bs02_mode = user_id != ""  # If general user_id is not set
            await coap_brssi(devices)

            if datetime.datetime.now().minute % brip_freq == 0 or first_run:
                first_run = False
                await asyncio.sleep(5)
                if not first_run: await coap_multicast_ip()
                await asyncio.sleep(10)
                await coap_light(1 if bs02_mode else 0, devices)  # Turn on light and start scan or off

            # Avvia il task per la copia del file in background
            asyncio.create_task(copy_file_after_delay(temp_file, final_file, 30))

        await asyncio.sleep(brssi_freq)

async def reset_ipv6_addresses():
	with open(config_filename, 'r+') as f:
		data = json.load(f)
		devices = data.get("devices", [])
		for device in devices:
			if(device.get('type') == "bs02"): device['ipv6'] = ""
		f.seek(0)
		json.dump(data, f, indent=4)
		f.truncate()

async def update_ipv6_address(mac_address, new_ipv6):
    print("AGGIORNO UN IP ADDRESS")
    with open(config_filename, 'r+') as f:
        # Load the current data from the configuration file
        data = json.load(f)
        devices = data.get("devices", [])
        
        # Update the IPv6 address for the device with the specified MAC address
        updated = False
        for device in devices:
            if device.get('mac') == mac_address:
                device['ipv6'] = new_ipv6
                updated = True
                break
        
        # Save the updated data back to the file
        if updated:
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()
        else:
            print("No device found with the specified MAC address.")

def validate_json(file_path):
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, FileNotFoundError) as e:
        custom_print(f"Invalid JSON or file not found at {file_path}: {e}")
        return False

async def start_api():
	global conn
	try:
		port = os.environ.get('API_PORT', "9000")
		app = web.Application()
		app.add_routes([web.get('/commission', handle),
					web.get('/uncommission', handle),
					web.get('/getdevice', handle),
					web.get('/langbangle', handle),
					web.get('/getupdates', handle),
					web.get('/buzz', handle),
					web.get('/restart', handle),
					web.get('/setusermode', handle),
					web.get('/changeuserid', handle),
					web.get('/calibratepositioning', handle),
     				web.get('/editpositioning', handle),
					web.get('/set_room_info', handle),
					web.get('/slowcalibration', handle),
					])
		event_loop = asyncio.get_event_loop()

		runner = web.AppRunner(app)
		await runner.setup()
		site = web.TCPSite(runner, '0.0.0.0', port)
		await site.start()
  
		# SETUP DB DATI STORICI
		conn = create_connection(database)

		# Creare le tabelle
		if conn is not None:
			create_tables(conn)
		else:
			print("Errore! Impossibile creare la connessione al database.")
  
		try:
			# chiamata per ottenere ipv6
			global ipv6_wpan0
			ipv6_wpan0 = get_ipv6_wpan0()
			if ipv6_wpan0:
				custom_print("***** Server for Openthread request Started *****")
				custom_print(data_ora_corrente())
				custom_print("*** IPv6 wpan0: " + ipv6_wpan0 + " Mac eth0: " + eth0_mac +" Org ID: " + get_org_id() +" ****")
				# Resource tree creation
				root = resource.Site()
				root.add_resource(['storedata'], AlarmResource())
				root.add_resource(['nodeip'], NodeIp())
				root.add_resource(['storebrssi'], StorebRssi())
				root.add_resource(['banglealarm'], BangleAlarm())
				root.add_resource(['bangletime'], BangleTime())
				root.add_resource(['bs02booted'], Bs02Booted())
				root.add_resource(['calibratedata'], CalibrateData())
				global context
				context = await aiocoap.Context.create_server_context(root, bind=(ipv6_wpan0, 5683))
				await reset_ipv6_addresses()
    
				t3 = event_loop.create_task(multicast_brssi_periodically())
				# t5 = event_loop.create_task(reset_dict_periodically())
        
				await asyncio.gather(
					t3
				)
			else:
				raise Exception("Nessun indirizzo IPv6 trovato per wpan0")
		except Exception as e:
			custom_print(f"Error in start_api: {e}")
	except Exception as e:
		custom_print(f"Error in start_api: {e}")

if __name__ == "__main__":
	try:
		loop = asyncio.get_event_loop()
		loop.run_until_complete(start_api())
		loop.run_forever()
	except KeyboardInterrupt:
		pass
	finally:
		loop.close()