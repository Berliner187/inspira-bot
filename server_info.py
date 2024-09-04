from datetime import datetime as prog_start
import datetime
import time
import gc
import platform
import sys

import psutil


__version__ = '1.0.0'


def timing_decorator(func):
    def wrapper(*args, **kwargs):
        start_time = time.monotonic()
        result = func(*args, **kwargs)
        end_time = time.monotonic()
        timing = abs(round(start_time - end_time, 3))
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S - %d.%m')}] {func.__name__} --- {timing} сек")
        return result
    return wrapper


class MachineResources:
    def get_memory_info(self):
        # RAM ПАМЯТЬ
        process = psutil.Process()
        memory_info = process.memory_info()

        ram_info = psutil.virtual_memory()
        total_memory = ram_info.total

        return f"{self.__format_size(memory_info.rss)} ({ram_info.percent}%) из {self.__format_size(total_memory)}"

    @staticmethod
    def get_disk_info():
        # ROM ПАМЯТЬ
        disk_usage = psutil.disk_usage('/')

        total = disk_usage.total
        used = disk_usage.used
        free = disk_usage.free
        percent = disk_usage.percent

        def format_size(size):
            units = ['байт', 'КБ', 'МБ', 'ГБ', 'ТБ']
            order = 0
            while size >= 1024 and order < len(units) - 1:
                size /= 1024
                order += 1
            size = round(size, 2)
            return f"{size} {units[order]}"

        total = format_size(total)
        used = format_size(used)
        free = format_size(free)

        return f"Занято {used} ({percent}%) из {total} |\n{free} свободно"

    @staticmethod
    def get_operations():
        # ОПЕРАЦИИ
        disk_io_counters = psutil.disk_io_counters()

        read_count = disk_io_counters.read_count
        write_count = disk_io_counters.write_count
        read_bytes = disk_io_counters.read_bytes
        write_bytes = disk_io_counters.write_bytes

        def format_disk_usage(number):
            if number >= 10 ** 9:
                return f"{number // 10 ** 9} млрд"
            elif number >= 10 ** 6:
                return f"{number // 10 ** 6} млн"
            elif number >= 10 ** 3:
                return f"{number // 10 ** 3} тыс"
            else:
                return str(number)

        read_count = format_disk_usage(read_count)
        write_count = format_disk_usage(write_count)
        read_bytes = format_disk_usage(read_bytes)
        write_bytes = format_disk_usage(write_bytes)

        return f"read---count={read_count}\nwrite_count={write_count}\nread_bytes={read_bytes}\nwrite_bytes={write_bytes}"

    @staticmethod
    def get_uptime():
        # UPTIME
        _process = psutil.Process()
        create_time = prog_start.fromtimestamp(_process.create_time())
        uptime = prog_start.now() - create_time
        return str(uptime).split('.')[0]

    @staticmethod
    def get_cpu_info():
        # ПРОЦЕССОР
        cpu_percent = psutil.cpu_percent(percpu=True)
        cpu_freq = psutil.cpu_freq(percpu=True)

        cpu_info = ""
        for i, (percent, freq) in enumerate(zip(cpu_percent, cpu_freq), start=1):
            cpu_info += f"Ядро {i}:   Загрузка: {percent:.2f}%\n"
        return cpu_info

    @staticmethod
    def __format_size(size_bytes):
        kb = 1024
        mb = kb * 1024
        gb = mb * 1024

        if size_bytes < kb:
            return f"{size_bytes} bytes"
        elif size_bytes < mb:
            return f"{size_bytes / kb:.2f} KB"
        elif size_bytes < gb:
            return f"{size_bytes / mb:.2f} MB"
        else:
            return f"{size_bytes / gb:.2f} GB"

    def get_sizes_objects(self):
        all_objects = gc.get_objects()
        total_size = sum(sys.getsizeof(obj) for obj in all_objects)

        output = f"{self.__format_size(total_size)}"
        print(output)
        return output

    def get_all_info(self):
        # СВОДКА ПО ВСЕМ
        return f"[{prog_start.now().strftime('%H:%M:%S - %d.%m')}]\n" \
               f"RAM\n{self.get_memory_info()}\n" \
               f"---------------------------\n" \
               f"ROM\n{self.get_disk_info()}\n" \
               f"---------------------------\n" \
               f"CPU\n{self.get_cpu_info()}" \
               f"---------------------------\n" \
               f"Sizes structures in memory\n{self.get_sizes_objects()}\n" \
               f"---------------------------\n" \
               f"UPTIME\n{str(self.get_uptime())}"

    @staticmethod
    def get_info_about_machine():
        my_system = platform.uname()

        print(f"System: {my_system.system}")
        print(f"Release: {my_system.release}")
        print(f"Node Name: {my_system.node}")
        print(f"Version: {my_system.version}")
        print(f"Machine: {my_system.machine}")
        print(f"Processor: {my_system.processor}")


def machine_res():
    machine_resources = MachineResources()
    sent_message = machine_resources.get_all_info()
    print(sent_message)
