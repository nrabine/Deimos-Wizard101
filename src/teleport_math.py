import asyncio
from wizwalker import XYZ, Client, Keycode
from wizwalker.file_readers.wad import Wad
import math
import struct
from io import BytesIO
from typing import Tuple, Union
from src.utils import is_free, get_quest_name, is_visible_by_path, get_popup_title
from src.paths import npc_range_path

type_format_dict = {
"char": "<c",
"signed char": "<b",
"unsigned char": "<B",
"bool": "?",
"short": "<h",
"unsigned short": "<H",
"int": "<i",
"unsigned int": "<I",
"long": "<l",
"unsigned long": "<L",
"long long": "<q",
"unsigned long long": "<Q",
"float": "<f",
"double": "<d",
}




class TypedBytes(BytesIO):
	def split(self, index: int) -> Tuple["TypedBytes", "TypedBytes"]:
		self.seek(0)
		buffer = self.read(index)
		return type(self)(buffer), type(self)(self.read())
	def read_typed(self, type_name: str):
		type_format = type_format_dict[type_name]
		size = struct.calcsize(type_format)
		data = self.read(size)
		return struct.unpack(type_format, data)[0]


# implemented from https://github.com/PeechezNCreem/navwiz/
# this licence covers the below function
# Boost Software License - Version 1.0 - August 17th, 2003
#
# Permission is hereby granted, free of charge, to any person or organization
# obtaining a copy of the software and accompanying documentation covered by
# this license (the "Software") to use, reproduce, display, distribute,
# execute, and transmit the Software, and to prepare derivative works of the
# Software, and to permit third-parties to whom the Software is furnished to
# do so, all subject to the following:
#
# The copyright notices in the Software and this entire statement, including
# the above license grant, this restriction and the following disclaimer,
# must be included in all copies of the Software, in whole or in part, and
# all derivative works of the Software, unless such copies or derivative
# works are solely in the form of machine-executable object code generated by
# a source language processor.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, TITLE AND NON-INFRINGEMENT. IN NO EVENT
# SHALL THE COPYRIGHT HOLDERS OR ANYONE DISTRIBUTING THE SOFTWARE BE LIABLE
# FOR ANY DAMAGES OR OTHER LIABILITY, WHETHER IN CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

def parse_nav_data(file_data: Union[bytes, TypedBytes]):
	# ty starrfox for remaking this
	if isinstance(file_data, bytes):
		file_data = TypedBytes(file_data)
	vertex_count = file_data.read_typed("short")
	vertex_max = file_data.read_typed("short")
	# unknown bytes
	file_data.read_typed("short")
	vertices = []
	idx = 0
	while idx <= vertex_max - 1:
		x = file_data.read_typed("float")
		y = file_data.read_typed("float")
		z = file_data.read_typed("float")
		vertices.append(XYZ(x, y, z))
		vertex_index = file_data.read_typed("short")
		if vertex_index != idx:
			vertices.pop()
			vertex_max -= 1
		else:
			idx += 1
	edge_count = file_data.read_typed("int")
	edges = []
	for idx in range(edge_count):
		start = file_data.read_typed("short")
		stop = file_data.read_typed("short")
		edges.append((start, stop))
	return vertices, edges


def calc_PointOn3DLine(xyz_1 : XYZ, xyz_2 : XYZ, additional_distance):
	# extends a point on the line created by 2 XYZs by additional_distance. xyz_1 is the origin.
	distance = calc_Distance(xyz_1, xyz_2)
	# distance = math.sqrt((pow(xyz_1.x - xyz_2.x, 2.0)) + (pow(xyz_1.y - xyz_2.y, 2.0)) + (pow(xyz_1.z - xyz_2.z, 2.0)))
	# Doing a rough distance check here since XYZ's aren't always equal even if they have seemingly the same values
	if distance < 1.0:
		return xyz_1
	else:
		n = ((distance - additional_distance) / distance)
		return XYZ(x=((xyz_2.x - xyz_1.x) * n) + xyz_1.x, y=((xyz_2.y - xyz_1.y) * n) + xyz_1.y, z=((xyz_2.z - xyz_1.z) * n) + xyz_1.z)


def calc_multiplerPointOn3DLine(xyz_1 : XYZ, xyz_2 : XYZ, multiplier : float):
	# extends a point on the line created by 2 XYZs by a multiplier. xyz_1 is the origin.
	return XYZ(x=((xyz_2.x - xyz_1.x) * multiplier) + xyz_1.x, y=((xyz_2.y - xyz_1.y) * multiplier) + xyz_1.y, z=((xyz_2.z - xyz_1.z) * multiplier) + xyz_1.z)


def calc_MidPoint(xyz_1 : XYZ, xyz_2 : XYZ, distance_multiplier : float = 0.5):
	# calculates the midpoint of 2 XYZs. 
	distance = math.sqrt((pow(xyz_1.x - xyz_2.x, 2.0)) + (pow(xyz_1.y - xyz_2.y, 2.0)) + (pow(xyz_1.z - xyz_2.z, 2.0)))
	n = distance_multiplier
	return XYZ(x=((xyz_2.x - xyz_1.x) * n) + xyz_1.x, y=((xyz_2.y - xyz_1.y) * n) + xyz_1.y, z=((xyz_2.z - xyz_1.z) * n) + xyz_1.z)


def calc_AveragePoint(xyz_list : list[XYZ]):
	# calculates the "midpoint" of a list of XYZs. 
	x_list = [x.x for x in xyz_list]
	y_list = [y.y for y in xyz_list]
	z_list = [z.z for z in xyz_list]
	return XYZ(x=(sum(x_list) / len(x_list)), y=(sum(y_list) / len(y_list)), z=(sum(z_list) / len(z_list)))


def rotate_point(origin_xyz : XYZ, point_xyz : XYZ, theta):
	# rotates point_xyz about origin_xyz, by theta degrees counterclockwise. This doesn't take the Z into account, so don't use this for anything that needs the Z to rotate.
	radians = math.radians(theta)
	cos = math.cos(radians)
	sin = math.sin(radians)
	y_diff = point_xyz.y - origin_xyz.y
	x_diff = point_xyz.x - origin_xyz.x
	x = cos * x_diff - sin * y_diff + origin_xyz.x
	y = sin * x_diff + cos * y_diff + origin_xyz.y
	return XYZ(x=x, y=y, z=point_xyz.z)


def are_xyzs_within_threshold(xyz_1 : XYZ, xyz_2 : XYZ, threshold : int = 200):
	# checks if 2 xyz's are within a rough distance threshold of each other. Not actual distance checking, but precision isn't needed for this, this exists to eliminate tiny variations in XYZ when being sent back from a failed port.
	threshold_check = [abs(abs(xyz_1.x) - abs(xyz_2.x)) < threshold, abs(abs(xyz_1.y) - abs(xyz_2.y)) < threshold, abs(abs(xyz_1.z) - abs(xyz_2.z)) < threshold]
	return all(threshold_check)


def calc_Distance(xyz_1 : XYZ, xyz_2 : XYZ):
	# calculates the distance between 2 XYZs
	return math.sqrt((pow(xyz_1.x - xyz_2.x, 2.0)) + (pow(xyz_1.y - xyz_2.y, 2.0)) + (pow(xyz_1.z - xyz_2.z, 2.0)))


def calc_squareDistance(xyz_1 : XYZ, xyz_2 : XYZ):
	# calculates the distance between 2 XYZs, but doesn't square root the answer to be much more efficient. Useful for comparing distances, not much else.
	return (pow(xyz_1.x - xyz_2.x, 2.0)) + (pow(xyz_1.y - xyz_2.y, 2.0)) + (pow(xyz_1.z - xyz_2.z, 2.0))


async def calc_up_XYZ(client: Client, xyz : XYZ = None, speed_constant : int = 580, speed_adjusted : bool = True):
	# handles optional xyz param, will default to using the position of the client
	if not xyz:
		client_xyz = await client.body.position()
	else:
		client_xyz = xyz

	# handles speed adjustment param
	if speed_adjusted:	
		additional_speed = await client.client_object.speed_multiplier()
	else:
		additional_speed = 0

	# adjusts speed constant based on speed multiplier, and adds it to the Z value
	new_z = client_xyz.z + (speed_constant * ((additional_speed / 100) + 1))

	return XYZ(x=client_xyz.x, y=client_xyz.y, z=new_z)


async def calc_FrontalVector(client: Client, xyz : XYZ = None, yaw : float = None, speed_constant : int = 580, speed_adjusted : bool = True, length_adjusted : bool = True):
	# handle if it is adjusted via speed multiplier or just uses the set constant
	if speed_adjusted:
		current_speed = await client.client_object.speed_multiplier()
	else:
		current_speed = 0

	# handles optional xyz param, will default to using the position of the client
	if not xyz:
		xyz = await client.body.position()

	# handles optional yaw paraam, will default to using the yaw of the client
	if not yaw:
		yaw = await client.body.yaw()
	else:
		yaw = yaw

	# adjust the speed constant based on the speed multiplier
	additional_distance = speed_constant * ((current_speed / 100) + 1)

	# calculate point "in front" of XYZ/client using yaw 
	frontal_x = (xyz.x - (additional_distance * math.sin(yaw)))
	frontal_y = (xyz.y - (additional_distance * math.cos(yaw)))
	frontal_xyz = XYZ(x=frontal_x, y=frontal_y, z=xyz.z)

	# make a length adjustment since diagonal movements 
	if length_adjusted:
		distance = calc_Distance(xyz, frontal_xyz)
		final_xyz = calc_PointOn3DLine(xyz_1=xyz, xyz_2=frontal_xyz, additional_distance=(additional_distance - distance))
	else:
		final_xyz = frontal_xyz

	return final_xyz


async def teleport_move_adjust(client: Client, xyz : XYZ, delay : float = 0.7, pet_mode: bool = False):
	# teleports the client to a given XYZ, and jitters afterward to actually update the position
	npc_check = await is_visible_by_path(client, npc_range_path)
	popup_str = None
	if npc_check:
		popup_str = await get_popup_title(client)
	if await is_free(client):
		try:
			if not pet_mode:
				await client.teleport(xyz, wait_on_inuse= True, purge_on_after_unuser_fixer= True)
			else:
				await client.pet_teleport(xyz, wait_on_inuse= True, purge_on_after_unuser_fixer= True)

				await asyncio.sleep(0.3)
				if not await is_visible_by_path(client, npc_range_path):
					if popup_str and popup_str != await get_popup_title(client):
						await client.send_key(Keycode.A, 0.05)
						await client.send_key(Keycode.D, 0.05)

		except ValueError:
			pass

	await asyncio.sleep(delay)


async def is_teleport_valid(client: Client, destination_xyz : XYZ, origin_xyz : XYZ):
	# checks if a client actually teleported to its destination.
	original_zone_name = await client.zone_name()
	await teleport_move_adjust(destination_xyz)

	# we know the teleport didn't succeed if we are very close to where we were, and the zone name hasn't changed
	if are_xyzs_within_threshold(await client.body.position(), origin_xyz, 50) and await client.zone_name() == original_zone_name:
		return False
	else:
		return True


async def auto_adjusting_teleport(client: Client, quest_position: XYZ = None):
	# DEPRECATED: Uses brute forcing XYZs in an alternating spiral pattern to find usable coords to port to. VERY slow.
	original_zone_name = await client.zone_name()
	original_position = await client.body.position()
	if not quest_position:
		quest_position = await client.quest_position.position()
	adjusted_position = quest_position
	mod_amount = 50
	current_angle = 0
	await teleport_move_adjust(client, quest_position)
	while are_xyzs_within_threshold((await client.body.position()), original_position, 50) and await client.zone_name() == original_zone_name:
		adjusted_position = calc_PointOn3DLine(original_position, quest_position, mod_amount)
		rotated_position = rotate_point(quest_position, adjusted_position, current_angle)
		await teleport_move_adjust(client, rotated_position)
		mod_amount += 100
		current_angle += 92


async def load_wad(path: str):
	if path is not None:
		return Wad.from_game_data(path.replace("/", "-"))


async def get_navmap_data(client: Client, zone: str = None) -> list[XYZ]:
	if not zone:
		zone = await client.zone_name()

	wad = await load_wad(zone)
	nav_data = await wad.get_file("zone.nav")
	vertices = []
	try:
		vertices, _ = parse_nav_data(nav_data)
	except:
		raise Exception('Zone did not have valid navmap data')

	return vertices


async def split_walk(client: Client, xyz: XYZ = None, segments: int = 5, original_zone: str = None):
	if not original_zone:
		original_zone = await client.zone_name()

	if not xyz:
		xyz = await client.quest_position.position()

	# walks to desired XYZ, only if the zone hasn't changed and if the param is enabled.

	current_pos = await client.body.position()
	points_on_line = [calc_multiplerPointOn3DLine(xyz_1=current_pos, xyz_2=xyz, multiplier=((i + 1) / segments)) for i in range(segments - 2)]
	points_on_line.append(xyz)
	for point_xyz in points_on_line:
		# print('for loop for split walking')
		if not await is_free(client) or await client.zone_name() != original_zone:
			break

		try:
			await client.goto(point_xyz.x, point_xyz.y)
		except:
			pass
		await asyncio.sleep(0)


async def navmap_tp(client: Client, xyz: XYZ = None, minimum_distance_increment: int = 250, walk_after=True, pet_mode: bool = False, auto_quest_leader: bool = False):
	if await is_free(client):
		original_zone_name = await client.zone_name()
		original_quest_xyz = await client.quest_position.position()
		original_quest_objective = await get_quest_name(client)
		original_position = await client.body.position()
		if xyz:
			quest_pos = xyz
		else:
			quest_pos = await client.quest_position.position()

		minimum_vertex_distance = minimum_distance_increment
		await teleport_move_adjust(client, quest_pos, pet_mode=pet_mode)
		while not await is_free(client):
			await asyncio.sleep(0.1)
		current_zone = await client.zone_name()
		navmap_errored = False
		try:
			wad = await load_wad(current_zone)
			nav_data = await wad.get_file("zone.nav")
			vertices = []
			vertices, _ = parse_nav_data(nav_data)
		except:
			await auto_adjusting_teleport(client)
			if walk_after:
				navmap_errored = True
				await split_walk(client, quest_pos, original_zone=original_zone_name)
		squared_distances = [calc_squareDistance(quest_pos, n) for n in vertices]
		sorted_distances = sorted(squared_distances)
		while not navmap_errored:
		# while are_xyzs_within_threshold(xyz_1=(await client.body.position()), xyz_2=original_position, threshold=100) and await client.zone_name() == original_zone_name and not await client.is_loading():
			current_pos = await client.body.position()
			if await client.zone_name() == original_zone_name and await is_free(client):
				if are_xyzs_within_threshold(xyz_1=current_pos, xyz_2=original_position, threshold=100):
					pass
				else:
					break
			else:
				break
			# set minimum distance between 2 chosen vertices
			minimum_vertex_distance += minimum_distance_increment
			for s in sorted_distances:
				current_index = sorted_distances.index(s)
				if current_index + 1 < len(sorted_distances):
					# this is REALLY inefficient but I'll fix it later maybe
					# selection of the 2 closest vertices that satisfy the criteria
					vertex = vertices[int(squared_distances.index(sorted_distances[current_index]))]
					next_vertex = vertices[int(squared_distances.index(sorted_distances[current_index + 1]))]
					between_vertices = calc_Distance(vertex, next_vertex)
					quest_to_vertex = calc_Distance(quest_pos, next_vertex)
					if between_vertices >= quest_to_vertex or between_vertices < minimum_vertex_distance:
						pass
					elif between_vertices < quest_to_vertex and between_vertices >= minimum_vertex_distance:
						adjusted_pos = calc_AveragePoint([vertex, next_vertex, quest_pos, quest_pos])
						final_adjusted_pos = XYZ(x=adjusted_pos.x, y=adjusted_pos.y, z=max([quest_pos.z, adjusted_pos.z]))
						if await client.zone_name() == original_zone_name and await is_free(client):
							await teleport_move_adjust(client, final_adjusted_pos, pet_mode=pet_mode)
						elif not await is_free(client):
							break
						break
					else:
						pass
				else:
					break

		if walk_after:
			await split_walk(client, quest_pos, original_zone=original_zone_name)
		await asyncio.sleep(0.3)

		# auto quest with leader needs to keep control of its follower clients, so skip walk_after
		if not auto_quest_leader:
			current_pos = await client.body.position()
			current_quest_xyz = await client.quest_position.position()
			current_quest_objective = await get_quest_name(client)
			current_zone = await client.zone_name()
			original_stats = [original_quest_objective, original_zone_name]
			current_stats = [current_quest_objective, current_zone]

			if all([await is_free(client), not await is_visible_by_path(client, npc_range_path), are_xyzs_within_threshold(original_quest_xyz, current_quest_xyz, 50), current_stats == original_stats]):
				await auto_adjusting_teleport(client)
				if walk_after:
					await split_walk(client, quest_pos, original_zone=original_zone_name)


def align_points(input_points: list[XYZ], map_points: list[XYZ]) -> list[XYZ]:
	# Aligns a list of inputs points to their closest neighbors in a list of map points.
	aligned_points = []
	for pos in input_points:
		minimum_distance = calc_Distance(pos, map_points[0])
		closest_map_point = map_points[0]

		for map_pos in map_points:
			distance = calc_Distance(pos, map_points)
			if distance < minimum_distance:
				minimum_distance = distance
				closest_map_point = map_pos

		aligned_points.append(closest_map_point)

	return aligned_points


def calc_chunks(points: list[XYZ], origin: XYZ = XYZ(x=0.0, y=0.0, z=0.0), entity_distance: float = 3147.0) -> list[XYZ]:
	# Returns a list of center points of "chunks" of the map, as defined by the input points.
	x1 = origin
	y1 = origin
	x2 = origin
	y2 = origin

	for xyz in points:
		if xyz.x < x1.x:
			x1 = xyz
		if xyz.y < y1.y:
			y1 = xyz
		if xyz.x > x2.x:
			x2 = xyz
		if xyz.y > y2.y:
			y2 = xyz

	least_point = XYZ(x1.x, y1.y, origin.z)
	most_point = XYZ(x2.x, y2.y, origin.z)

	max_radius = max([calc_Distance(origin, least_point), calc_Distance(origin, most_point)])
	max_radius -= entity_distance

	entity_diameter = entity_distance * 2

	current_radius = entity_diameter

	chunk_points = [origin]

	iterations = math.ceil(max_radius / current_radius)
	print(f'Iterations: {iterations}')
	for _ in range(iterations):
		circumference = (2.0 * math.pi) * current_radius
		sides = math.ceil(circumference / entity_diameter)
		print(f'Sides: {sides}')
		angle_increment = 360 / sides

		frontal_y = origin.y - current_radius
		frontal_xyz = XYZ(origin.x, frontal_y, origin.z)

		for s in range(sides):
			if s != 0:
				angle = angle_increment * s
				rotated_pos = rotate_point(origin, frontal_xyz, angle)
				if calc_squareDistance(rotated_pos, origin) <= calc_squareDistance(most_point, origin):
					chunk_points.append(rotated_pos)

		current_radius += entity_diameter

	print(f'chunks:{len(chunk_points)}')
	return chunk_points


async def collision_tp(client, xyz):
	pass


def calc_angle(p1 : XYZ, p2 : XYZ, p3 : XYZ = None):
	if not p3:
		p3 = XYZ(x=p1.x, y=p2.y, z=p1.z)
	return math.degrees(math.atan2(p3.y - p1.y, p3.x - p1.x) - math.atan2(p2.y - p1.y, p2.x - p1.x))