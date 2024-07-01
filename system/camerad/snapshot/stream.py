#!/usr/bin/env python3
import subprocess
import time
import requests
import threading
import sys


import numpy as np
from PIL import Image

import cereal.messaging as messaging
from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.system.hardware import PC
from openpilot.selfdrive.controls.lib.alertmanager import set_offroad_alert
from openpilot.system.manager.process_config import managed_processes


VISION_STREAMS = {
  "roadCameraState": VisionStreamType.VISION_STREAM_ROAD,
  "driverCameraState": VisionStreamType.VISION_STREAM_DRIVER,
  "wideRoadCameraState": VisionStreamType.VISION_STREAM_WIDE_ROAD,
}

url="http://127.0.0.1:11111/roadCameraState"
# 构建请求头
headers = {
  'Authorization': 'JWT eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3MjQxMTc4NjAsIm5iZiI6MTcxNjM0MTg2MCwiaWF0IjoxNzE2MzQxODYwLCJpZGVudGl0eSI6IjkxZTAyZmU2MTM0OTMzMTYifQ.gu_MiqtdBIvFPUqvkSdalolIhxTwzf9hYdCIfWjMnOU '
}


def jpeg_write(fn, dat):
  img = Image.fromarray(dat)
  img.save(fn, "JPEG")


def yuv_to_rgb(y, u, v):
  ul = np.repeat(np.repeat(u, 2).reshape(u.shape[0], y.shape[1]), 2, axis=0).reshape(y.shape)
  vl = np.repeat(np.repeat(v, 2).reshape(v.shape[0], y.shape[1]), 2, axis=0).reshape(y.shape)

  yuv = np.dstack((y, ul, vl)).astype(np.int16)
  yuv[:, :, 1:] -= 128

  m = np.array([
    [1.00000,  1.00000, 1.00000],
    [0.00000, -0.39465, 2.03211],
    [1.13983, -0.58060, 0.00000],
  ])
  rgb = np.dot(yuv, m).clip(0, 255)
  return rgb.astype(np.uint8)


def extract_image(buf):
#      buf = front
  y = np.array(buf.data[:buf.uv_offset], dtype=np.uint8).reshape((-1, buf.stride))[:buf.height, :buf.width]
  u = np.array(buf.data[buf.uv_offset::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]
  v = np.array(buf.data[buf.uv_offset+1::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]

  try:
    d = np.append(y,u)
    d = np.append(d,v)
    response = requests.put(url, data=bytes(d), headers=headers, timeout=1)
    if response.status_code == 200:
      pass#print('PUT请求成功')
    else:
      print('PUT请求失败')
  except TimeoutError:
    print("Timeout, put..000000000000000000000000000000000000000000000000.")

  return

  return yuv_to_rgb(y, u, v)


def extract_image_pic(buf):
  y = np.array(buf.data[:buf.uv_offset], dtype=np.uint8).reshape((-1, buf.stride))[:buf.height, :buf.width]
  u = np.array(buf.data[buf.uv_offset::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]
  v = np.array(buf.data[buf.uv_offset+1::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]

  return yuv_to_rgb(y, u, v)

def get_snapshots(frame="roadCameraState", front_frame="driverCameraState"):
  sockets = [s for s in (frame, front_frame) if s is not None]
  sm = messaging.SubMaster(sockets)
  vipc_clients = {s: VisionIpcClient("camerad", VISION_STREAMS[s], True) for s in sockets}

  # wait 4 sec from camerad startup for focus and exposure
  while sm[sockets[0]].frameId < int(4. / DT_MDL):
    sm.update()

  for client in vipc_clients.values():
    client.connect(True)

  # grab images
  rear, front = None, None
  # if frame is not None:
  #   c = vipc_clients[frame]
  #   while True:
  #     rear = extract_image(c.recv())

  if front_frame is not None:
    #c = vipc_clients[front_frame]
    c = vipc_clients[frame]
    while True:
      time_start = time.time()
      front = extract_image(c.recv())
      time_end = time.time()
      cost = int(round(time_end * 1000))  - int(round(time_start * 1000))
      if cost < 50:
        print(50-cost)
        time.sleep(0.001*(50-cost-1))

  return
  return rear, front

def get_snapshots_pic(frame="roadCameraState", front_frame="driverCameraState", camera_is_running=False):
  sockets = [s for s in (frame, front_frame) if s is not None]
  sm = messaging.SubMaster(sockets)
  vipc_clients = {s: VisionIpcClient("camerad", VISION_STREAMS[s], True) for s in sockets}

  if camera_is_running:
    # wait 1 sec from camerad startup for focus and exposure
    while sm[sockets[0]].frameId < int(1 / DT_MDL):
      sm.update()
  else:
    # wait 1 sec from camerad startup for focus and exposure
    while sm[sockets[0]].frameId < int(1. / DT_MDL):
      sm.update()

  for client in vipc_clients.values():
    client.connect(True)

  # grab images
  rear, front = None, None
  if frame is not None and int(sys.argv[1])==2:
    c = vipc_clients[frame]
    rear = extract_image_pic(c.recv())
  if front_frame is not None and int(sys.argv[1])==1:
    print("extract_image_pic")
    c = vipc_clients[front_frame]
    front = extract_image_pic(c.recv())
  return rear, front

def snapshot(arg):
  print(arg)
  params = Params()

  # if (not params.get_bool("IsOffroad")) or params.get_bool("IsTakingSnapshot"):
  #   print("Already taking snapshot")
  #   return None, None

  front_camera_allowed = True #params.get_bool("RecordFront")
  params.put_bool("IsTakingSnapshot", True)
  set_offroad_alert("Offroad_IsTakingSnapshot", True)
  #time.sleep(2.0)  # Give hardwared time to read the param, or if just started give camerad time to start

  # Check if camerad is already started
  camera_is_running = False
  try:
    subprocess.check_call(["pgrep", "camerad"])
    camera_is_running = True
    print("Camerad already running")
    #params.put_bool("IsTakingSnapshot", False)
    #params.remove("Offroad_IsTakingSnapshot")
    #return None, None
  except subprocess.CalledProcessError:
    pass

  try:
    # Allow testing on replay on PC
    if not PC and not camera_is_running:
      managed_processes['camerad'].start()

    frame = "wideRoadCameraState"
    #frame = "roadCameraState"

    front_frame = "driverCameraState" if front_camera_allowed else None
    #stream
    #get_snapshots(frame, front_frame)

    #picture
    rear, front = get_snapshots_pic(frame, front_frame, camera_is_running)
    if rear is not None:
      jpeg_write("/tmp/back.jpg", rear)
    if front is not None:
      jpeg_write("/tmp/front.jpg", front)

  finally:
    #managed_processes['camerad'].stop()
    params.put_bool("IsTakingSnapshot", False)
    set_offroad_alert("Offroad_IsTakingSnapshot", False)

  if not front_camera_allowed:
    front = None

  #return rear, front


if __name__ == "__main__":
  # t = threading.Thread(target=snapshot, args=(0, ))
  # t.daemon = True
  # t.start()
  # time.sleep(3600)

  snapshot(sys.argv[1])

  # pic, fpic = snapshot()
  # if pic is not None:
  #   print(pic.shape)
  #   jpeg_write("/tmp/back.jpg", pic)
  #   if fpic is not None:
  #     jpeg_write("/tmp/front.jpg", fpic)
  # else:
  #   print("Error taking snapshot")

