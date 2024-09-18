#!/usr/bin/env python3
import os
import sys

from tracer import TracerManager, TRACER_FILE


__version__ = '1.0.0'


def system_action(parameter):
    if parameter == 'clear':
        os.system('clear && clear')
    elif parameter == 'restart':
        os.execv(sys.executable, [sys.executable] + sys.argv)


def display_funcs():
    print(f"\n\n• {__version__} ––– console_gui\n\n")
    array_funcs = {
        1: 'Load logger',
        9: 'Restart',
        0: 'Exit'
    }
    for key, value in array_funcs.items():
        print(f"[{key}] --- {value}")
    print()


def control_bus():
    user_actions = input("Change: ")
    if user_actions == "1":
        system_action('clear')
        tracer_manager = TracerManager(TRACER_FILE)
        tracer_manager.tracer_formatter_load()
    elif user_actions == "0":
        system_action('clear')
        quit()
    elif user_actions == "9":
        system_action('clear')
        system_action('restart')
    else:
        system_action('clear')
    display_funcs()
    control_bus()


if __name__ == '__main__':
    system_action('clear')
    display_funcs()
    control_bus()
