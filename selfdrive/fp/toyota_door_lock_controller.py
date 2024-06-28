#!/usr/bin/env python3


from cereal import car
from openpilot.common.conversions import Conversions as CV
from openpilot.common.params import Params
from openpilot.common.api import Api
import threading
import time



GearShifter = car.CarState.GearShifter
UNLOCK_CMD = b'\x40\x05\x30\x11\x00\x40\x00\x00'
LOCK_CMD = b'\x40\x05\x30\x11\x00\x80\x00\x00'
LOCK_AT_SPEED = 0 * CV.KPH_TO_MS


class DoorLockController:

    def __init__(self):
        self._dp_toyota_auto_lock_once = False
        self._gear_prev = GearShifter.park
        self._cmd = ""
        self._cmd_exec = True
    #    thread.start_new_thread(self.GetCMD, ( 2, ) )
        e = threading.Event()
        t = threading.Thread(target=self.GetCMD, args=( 2, ))
        try:
          t.start()
        finally:
          e.set()
          t.join()


    def GetCMD(self, arg):
        while True:
            if not self._cmd_exec:
                time.sleep(1)
                continue

            dongle_id = Params.get("DongleId", encoding='utf8')
            self.api = Api(dongle_id)
            try:
                self._cmd = self.api.get("getcmd/" + self.dongle_id + "/door", timeout=10, path="", access_token="")
                if self._cmd == "lock" or self._cmd == "unlock":
                    self._cmd_exec = False
            except Exception as e:
                print(f"ERROR: GetCMD \n", str(e))
            time.sleep(arg)

    def process(self, gear, v_ego, door_open):
        # dp - door auto lock / unlock logic
        # thanks to AlexandreSato & cydia2020
        # https://github.com/AlexandreSato/animalpilot/blob/personal/doors.py
        message = []

        if not door_open:
            if not self._cmd_exec: # exec remote cmd
                if self._cmd == "lock":
                    self._cmd = ""
                    self._cmd_exec = True
                    message = [0x750, LOCK_CMD, 0]
                    return message
                elif self._cmd == "unlock" and gear == GearShifter.park:
                    self._cmd = ""
                    self._cmd_exec = True
                    message = [0x750, UNLOCK_CMD, 0]
                    return message

            if gear == GearShifter.park and gear != self._gear_prev:
                #message = [0x750, UNLOCK_CMD, 0]
                self._dp_toyota_auto_lock_once = False
            elif gear == GearShifter.drive and not self._dp_toyota_auto_lock_once and v_ego >= LOCK_AT_SPEED:
                message = [0x750, LOCK_CMD, 0]
                self._dp_toyota_auto_lock_once = True
            self._gear_prev = gear
        return message

