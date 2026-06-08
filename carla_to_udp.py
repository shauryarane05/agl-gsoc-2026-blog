import carla, socket, json, time, random

client = carla.Client('localhost', 2000); client.set_timeout(20)
world = client.get_world()

# Clean up any leftover vehicles from previous crashed runs
existing = world.get_actors().filter('vehicle.*')
for a in existing:
    try: a.destroy()
    except Exception: pass
if len(existing): print("cleaned up", len(existing), "leftover vehicles")

bp = world.get_blueprint_library().filter('vehicle.tesla.model3')[0]
spawns = world.get_map().get_spawn_points()
random.shuffle(spawns)

ego = None
for sp in spawns:
    ego = world.try_spawn_actor(bp, sp)   # returns None on collision
    if ego is not None:
        break
if ego is None:
    raise RuntimeError("no free spawn point found")

ego.set_autopilot(True)
print("spawned ego:", ego.type_id, "id", ego.id)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); dst = ('127.0.0.1', 9870)
try:
    while True:
        tf = ego.get_transform(); v = ego.get_velocity()
        sock.sendto(json.dumps(dict(
            x=tf.location.x, y=tf.location.y, z=tf.location.z, yaw=tf.rotation.yaw,
            vx=v.x, vy=v.y, vz=v.z)).encode(), dst)
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    ego.destroy(); print("ego destroyed")
