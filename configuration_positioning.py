import csv
import os
import json
import aiocoap.resource as resource
import aiocoap

from database_manager import DatabaseManager


# Inizializza una lista per memorizzare i dati di calibrazione come dizionari
calibration_data = []

# Variabili globali per memorizzare lo stato corrente
current_room = ""
current_device = ""

start_path = ""

class CalibrateData(resource.Resource):
    """This resource supports the PUT method"""

    def __init__(self):
        super().__init__()

    async def render_put(self, request):
        global calibration_data, current_room, current_device
        payload = request.payload.decode('ascii')

        try:
            print("Received calibration data:")
            data = json.loads(payload)
            print("Received calibration data: {}".format(str(data)))
            for mac, rssi_values in data.items():
                rssi_string = json.dumps(rssi_values)
                new_row = {'mac_device': current_device, 'mac_bs': mac, 'room': current_room, 'rssi_values': rssi_string}
                calibration_data.append(new_row)
        except ValueError:
            print("ERROR IN CONVERTING RECEIVED JSON " + payload)
        
        return aiocoap.Message(code=aiocoap.CHANGED, payload="")

    async def save_calibration_data(self):
        global calibration_data
        if os.path.exists(start_path+'/shared_dir/calibration_results.csv'):
            os.remove(start_path+'/shared_dir/calibration_results.csv')
        with open(start_path+'/shared_dir/calibration_results.csv', mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['mac_device', 'mac_bs', 'room', 'rssi_values'], quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
            writer.writeheader()
            writer.writerows(calibration_data)
        print("Data saved to CSV file after configuring all rooms.")
        calibration_data = []

    def set_current_room(self, room):
        global current_room
        current_room = room

    def set_current_device(self, device):
        global current_device
        current_device = device

    async def load_calibration_data(self):
        global calibration_data, start_path
        # Check if calibration_data is already populated
        if calibration_data:
            print("Calibration data already loaded, skipping file load.")
            return
        
        try:
            with open(start_path+'/shared_dir/calibration_results.csv', mode='r', newline='') as file:
                reader = csv.DictReader(file)
                calibration_data = [row for row in reader]
            print("Data loaded from CSV file into calibration data array.")
        except FileNotFoundError:
            print("No existing calibration file found.")


    def remove_room_data(self, room):
        global calibration_data
        # Filtra i dati per mantenere solo quelli che non corrispondono alla stanza specificata
        calibration_data = [data for data in calibration_data if data['room'] != room]
        print(f"All data for room '{room}' has been removed from the calibration data array.")
        
    async def slow_calibration(self, mac_address, start_timestamp, end_timestamp, room):
        # Load existing calibration data from file
        await self.load_calibration_data()

        # Remove old data for the specified room
        global calibration_data
        calibration_data = [data for data in calibration_data if data['room'] != room]

        # Query database for new calibration data
        self.db_manager = DatabaseManager(start_path+"/shared_dir/DATISTORICI.db")
        query = """
        SELECT macBangle, rssiBangle, macBs02
        FROM datistorici_positioning
        WHERE timestamp BETWEEN ? AND ? AND macBangle = ?
        ORDER BY macBangle
        """
        cur = self.db_manager.conn.cursor()
        cur.execute(query, (int(start_timestamp), int(end_timestamp), str(mac_address)))
        rows = cur.fetchall()

        # Collect and aggregate new calibration data for the specified room
        new_calibration_results = {}
        for macBangle, rssiBangle, macBs02 in rows:
            if macBs02 not in new_calibration_results:
                new_calibration_results[macBs02] = []
            new_calibration_results[macBs02].append(abs(int(rssiBangle)))

        # Format the aggregated results and update the global calibration data
        for mac_bs, rssi_list in new_calibration_results.items():
            calibration_data.append({
                'mac_device': mac_address,
                'mac_bs': mac_bs,  # Use macBs02 as the base station identifier
                'room': room,
                'rssi_values': json.dumps(rssi_list)
            })

        # Save the updated calibration data to file
        await self.save_calibration_data()
        self.db_manager.close_connection()
        print("Updated calibration data for room '{}' with aggregated RSSI values.".format(room))
        