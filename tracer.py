import csv
import os
from datetime import datetime
from typing import List, Dict


TRACER_FILE = "logger.csv"
HEADERS_LOG_FILE = ["timestamp", "log_level", "user_id", "function", "message_text", "error_details", "additional_info"]


class TracerManager:
    def __init__(self, log_file):
        self.log_file = log_file
        self.default_color = self.format_hex_color("#FFFFFF")
        self.color_info = self.format_hex_color("#CAFFBF")
        self.color_warning = self.format_hex_color("#FBC330")
        self.color_error = self.format_hex_color("#F10C45")
        self.color_critical = self.format_hex_color("#FF073A")
        self.color_admin = self.format_hex_color("#2EE8BB")
        self.color_system = self.format_hex_color("#9B30FF")
        self.color_db = self.format_hex_color("#4F48EC")

    @staticmethod
    def format_hex_color(hex_color):
        """ Получение цвета в формате HEX """
        r, g, b = [int(hex_color[item:item+2], 16) for item in range(1, len(hex_color), 2)]
        return f"\x1b[38;2;{r};{g};{b}m".format(**vars())

    def __create_file_if_not_exists(self):
        if os.path.exists(self.log_file) is False:
            with open(self.log_file, "w") as log_file:
                headers = csv.writer(log_file)
                headers.writerow(HEADERS_LOG_FILE)
            log_file.close()

    def tracer_charge(self, log_level: str, user_id: int, function, message_text, error_details='', additional_info=''):
        self.__create_file_if_not_exists()
        with open(self.log_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                log_level,
                user_id,
                function,
                message_text,
                error_details,
                additional_info
            ])

    def tracer_load(self) -> List[Dict[str, str]]:
        logs = []
        with open(self.log_file, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            header = next(reader)
            for row in reader:
                log_entry = {
                    'timestamp': row[0],
                    'log_level': row[1],
                    'user_id': row[2],
                    'function': row[3],
                    'message_text': row[4],
                    'error_details': row[5],
                    'additional_info': row[6]
                }
                logs.append(log_entry)
        return logs

    def tracer_formatter_load(self) -> print:
        log_data = self.tracer_load()
        headers = ["Timestamp", "LOG LEVEL", "User ID", "Function", "Message Text", "Error Details", "Additional Info"]

        max_widths = [len(header) for header in headers]

        for log in log_data:
            max_widths[0] = max(max_widths[0], len(log['timestamp']))
            max_widths[1] = max(max_widths[1], len(log['log_level']))
            max_widths[2] = max(max_widths[2], len(log['user_id']))
            max_widths[3] = max(max_widths[3], len(log['function']))
            max_widths[4] = max(max_widths[4], len(log['message_text']))
            max_widths[5] = max(max_widths[5], len(log['error_details']))
            max_widths[6] = max(max_widths[6], len(log['additional_info']))

        header_format = " | ".join(f"{{:<{width}}}" for width in max_widths)
        print(header_format.format(*headers))
        print("-" * (sum(max_widths) + 3 * (len(headers) - 1)))

        for log in log_data:
            if log['log_level'] == 'WARNING':
                color = self.color_warning
            elif log['log_level'] == 'ERROR':
                color = self.color_error
            elif log['log_level'] == 'CRITICAL':
                color = self.color_critical
            elif log['log_level'] == 'ADMIN':
                color = self.color_admin
            elif log['log_level'] == 'SYSTEM':
                color = self.color_system
            elif log['log_level'] == 'DB':
                color = self.color_db
            else:
                color = self.color_info

            log_line = [
                log['timestamp'],
                log['log_level'],
                log['user_id'],
                log['function'],
                log['message_text'],
                log['error_details'],
                log['additional_info']
            ]

            log_format = " | ".join(f"{color}{{:<{width}}}{color}" for width in max_widths)
            print(log_format.format(*log_line), self.format_hex_color('#ffffff'))
