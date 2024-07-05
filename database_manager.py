import sqlite3
from sqlite3 import Error
import json

def is_number(s):
    """ Controlla se la stringa s può essere interpretata come un numero intero o decimale. """
    if s is None:
        return False  # None non è un numero
    try:
        float(s)  # per numeri interi e decimali
        return True
    except ValueError:
        return False

class DatabaseManager:
    def __init__(self, db_file):
        """ Inizializza il gestore del database con il file del database. """
        self.db_file = db_file
        self.conn = self.create_connection()

    def create_connection(self):
        """ Crea una connessione al database SQLite. """
        try:
            conn = sqlite3.connect(self.db_file, check_same_thread=False)
            print("Connessione riuscita. Versione SQLite:", sqlite3.version)
            return conn
        except Error as e:
            print(e)
            return None

    def create_table(self, table_name, json_data):
        """Crea una tabella dinamicamente basata sui campi del JSON, se non esiste."""
        fields = json_data[0].keys()
        field_definitions = []
        for field in fields:
            types_in_field = set(type(item[field]) for item in json_data)
            field_type = "TEXT"  # Default type if mixed types or contains strings
            
            if float in types_in_field or int in types_in_field:
                if types_in_field == {int} or types_in_field == {int, type(None)}:
                    field_type = "INTEGER"
                elif types_in_field == {float} or types_in_field == {float, type(None)} or types_in_field == {int, float, type(None)}:
                    field_type = "REAL"
            
            null_status = "NULL" if type(None) in types_in_field else "NOT NULL"
            field_definitions.append(f"{field} {field_type} {null_status}")

        field_definitions_str = ', '.join(field_definitions)
        sql_create_table = f"""CREATE TABLE IF NOT EXISTS {table_name} (
                                id INTEGER PRIMARY KEY,
                                {field_definitions_str}
                            );"""
        try:
            c = self.conn.cursor()
            c.execute(sql_create_table)
        except Error as e:
            print(e)

    def insert_json_data(self, table_name, json_data):
        """ Inserisce dati JSON nella tabella. Assicura prima che la tabella esista. """
        self.create_table(table_name, json_data)
        fields = json_data[0].keys()
        placeholders = ', '.join(['?' for _ in fields])
        sql = f"INSERT INTO {table_name}({', '.join(fields)}) VALUES({placeholders})"
        cur = self.conn.cursor()
        for data in json_data:
            values = tuple(data[field] if data[field] is not None else None for field in fields)
            cur.execute(sql, values)
        self.conn.commit()

    def close_connection(self):
        """ Chiude la connessione al database. """
        if self.conn:
            self.conn.close()
