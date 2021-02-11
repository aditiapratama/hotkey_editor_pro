bl_info = {
	"name": "Hotkey Editor Pro",
	"author": "Demeter Dzadik",
	"version": (1,0),
	"blender": (2, 92, 0),
	"location": "Edit > Preferences > Keymap > Hotkey Editor Pro",
	"description": "Reworked hotkey editor.",
	"category": "Interface",
	"doc_url": "https://github.com/Mets3D/hotkey_editor_pro",
	"tracker_url": "https://github.com/Mets3D/hotkey_editor_pro",
}

import bpy
from bpy.props import BoolProperty, CollectionProperty, PointerProperty, StringProperty, IntProperty
from rna_keymap_ui import _indented_layout
from bpy.app.translations import contexts as i18n_contexts
from bpy.app.translations import pgettext_iface as iface_

# Some terminology notes, looking at rna_keymap_ui.py:
# A "KeyMap" is what I would rather call a KeyMap Category, eg. "Window", "3D View", etc.
# I may need to add some properties to this bpy.type, since I want to be able to set one of these as selected, or to show a warning icon.

# A "KeyMapItem" is a single shortcut. I may need to abstract this, since I want a single entry of my Shortcut concept to be able to represent several Blender shortcuts.

"""Plan:
- Need to create a mapping from HEP category hierarchy to Blender categories. This may involve defining the names in two places if we want some clarity. Oh, well.
- This would be done by looking at the Blender hierarchy in keymap_hierarchy.py, then searching for the relevant WM_keymap_ensure function call, then going through each and determining which HEP category they belong to.

- Then, we would let Blender's recursive shortcut drawing function run, without the drawing part, to match the individual hotkey items to our categories.

- Then we can start displaying these hotkeys in a 2nd column, when the relevant HEP category is selected

- Then we can replace those real keymap entries with HEP keymap entries, of which there would have to be fewer, since their purpose is to mask duplicates.

HIERARCHY
	Pretty sure Blender's keymap category hierarchy is wrong or non-sensical in some cases.
	- What's the difference between Window and Screen?
	- What on earth is View2D Buttons List?
	- "Paint Vertex Selection (Weight, Vertex)" would be nice if it could be the child of two categories. So it could just be called "Paint Vertex Selection", but show up under both Weight and Vertex Paint (and therefore cause conflicts for both)
		This is already not supported since we save the parent category as a single string... -.-
	- Same for Paint Face Mask
	- Image Paint has an Image Paint (Global) despite not having any other categories....
	- I wonder when the "Animation" context is active... does Blender even know these things!? What a mess to untangle...

	All of this is stored in python in keymap_hierarchy.py. Shame it's a non-sensical hierarchy!
	Keymaps have a poll function, these would help determine a more legitimate hierarchy. Search the code for WM_keymap_ensure. After each, there should be a poll function specified.
	I think this can work but it will be pure old manual labour...

	So, we will probably end up creating our own keymap category hierarchy, that will be a total mish-mash of Blender's keymap categories.
	So, it would be good to make a mapping from our keymap categories to the list of blender keymap categories whose keymaps should be included within.
	WHAT A GLORIOUS MESS THIS WILL BE!
"""

drawn_keymap_categories = []

_EVENT_TYPES = set()
_EVENT_TYPE_MAP = {}
_EVENT_TYPE_MAP_EXTRA = {}

def draw_kmi(display_keymaps, kc, km, kmi, layout, level):
	map_type = kmi.map_type

	col = _indented_layout(layout, level)

	if kmi.show_expanded:
		col = col.column(align=True)
		box = col.box()
	else:
		box = col.column()

	split = box.split()

	# header bar
	row = split.row(align=True)
	row.prop(kmi, "show_expanded", text="", emboss=False)
	row.prop(kmi, "active", text="", emboss=False)

	if km.is_modal:
		row.separator()
		row.prop(kmi, "propvalue", text="")
	else:
		row.label(text=kmi.name)

	row = split.row()
	row.prop(kmi, "map_type", text="")
	if map_type == 'KEYBOARD':
		row.prop(kmi, "type", text="", full_event=True)
	elif map_type == 'MOUSE':
		row.prop(kmi, "type", text="", full_event=True)
	elif map_type == 'NDOF':
		row.prop(kmi, "type", text="", full_event=True)
	elif map_type == 'TWEAK':
		subrow = row.row()
		subrow.prop(kmi, "type", text="")
		subrow.prop(kmi, "value", text="")
	elif map_type == 'TIMER':
		row.prop(kmi, "type", text="")
	else:
		row.label()

	if (not kmi.is_user_defined) and kmi.is_user_modified:
		row.operator("preferences.keyitem_restore", text="", icon='BACK').item_id = kmi.id
	else:
		row.operator(
			"preferences.keyitem_remove",
			text="",
			# Abusing the tracking icon, but it works pretty well here.
			icon=('TRACKING_CLEAR_BACKWARDS' if kmi.is_user_defined else 'X')
		).item_id = kmi.id

	# Expanded, additional event settings
	if kmi.show_expanded:
		box = col.box()

		split = box.split(factor=0.4)
		sub = split.row()

		if km.is_modal:
			sub.prop(kmi, "propvalue", text="")
		else:
			# One day...
			# sub.prop_search(kmi, "idname", bpy.context.window_manager, "operators_all", text="")
			sub.prop(kmi, "idname", text="")

		if map_type not in {'TEXTINPUT', 'TIMER'}:
			sub = split.column()
			subrow = sub.row(align=True)

			if map_type == 'KEYBOARD':
				subrow.prop(kmi, "type", text="", event=True)
				subrow.prop(kmi, "value", text="")
				subrow_repeat = subrow.row(align=True)
				subrow_repeat.active = kmi.value in {'ANY', 'PRESS'}
				subrow_repeat.prop(kmi, "repeat", text="Repeat")
			elif map_type in {'MOUSE', 'NDOF'}:
				subrow.prop(kmi, "type", text="")
				subrow.prop(kmi, "value", text="")

			subrow = sub.row()
			subrow.scale_x = 0.75
			subrow.prop(kmi, "any", toggle=True)
			subrow.prop(kmi, "shift", toggle=True)
			subrow.prop(kmi, "ctrl", toggle=True)
			subrow.prop(kmi, "alt", toggle=True)
			subrow.prop(kmi, "oskey", text="Cmd", toggle=True)
			subrow.prop(kmi, "key_modifier", text="", event=True)

		# Operator properties
		box.template_keymap_item_properties(kmi)

		# Modal key maps attached to this operator
		if not km.is_modal:
			kmm = kc.keymaps.find_modal(kmi.idname)
			if kmm:
				draw_km(display_keymaps, kc, kmm, None, layout, level + 1)
				layout.context_pointer_set("keymap", km)

def draw_km(display_keymaps, kc, km, children, layout, level):
	global drawn_keymap_categories

	km = km.active()
	drawn_keymap_categories.append(km.name)

	layout.context_pointer_set("keymap", km)

	col = _indented_layout(layout, level)

	row = col.row(align=True)
	row.prop(km, "show_expanded_children", text="", emboss=False)
	row.label(text=km.name, text_ctxt=i18n_contexts.id_windowmanager)

	if km.is_user_modified or km.is_modal:
		subrow = row.row()
		subrow.alignment = 'RIGHT'

		if km.is_user_modified:
			subrow.operator("preferences.keymap_restore", text="Restore")
		if km.is_modal:
			subrow.label(text="", icon='LINKED')
		del subrow

	if km.show_expanded_children:
		if children:
			# Put the Parent key map's entries in a 'global' sub-category
			# equal in hierarchy to the other children categories
			subcol = _indented_layout(col, level + 1)
			subrow = subcol.row(align=True)
			subrow.prop(km, "show_expanded_items", text="", emboss=False)
			name = iface_("%s (Global)") % km.name
			subrow.label(text=name, translate=False)
			drawn_keymap_categories.append(name)
		else:
			km.show_expanded_items = True

		# Key Map items
		if km.show_expanded_items:
			kmi_level = level + 3 if children else level + 1
			for kmi in km.keymap_items:
				draw_kmi(display_keymaps, kc, km, kmi, col, kmi_level)

			# "Add New" at end of keymap item list
			subcol = _indented_layout(col, kmi_level)
			subcol = subcol.split(factor=0.2).column()
			subcol.operator("preferences.keyitem_add", text="Add New", text_ctxt=i18n_contexts.id_windowmanager,
							icon='ADD')

			col.separator()

		# Child key maps
		if children:
			for entry in children:
				draw_entry(display_keymaps, entry, col, level + 1)

		col.separator()

def draw_entry(display_keymaps, entry, col, level=0):
	idname, spaceid, regionid, children = entry

	for km, kc in display_keymaps:
		if km.name == idname and km.space_type == spaceid and km.region_type == regionid:
			draw_km(display_keymaps, kc, km, children, col, level)

def draw_filtered(display_keymaps, filter_type, filter_text, layout):
	if filter_type == 'NAME':
		def filter_func(kmi):
			return (filter_text in kmi.idname.lower() or
					filter_text in kmi.name.lower())
	else:
		if not _EVENT_TYPES:
			enum = bpy.types.Event.bl_rna.properties["type"].enum_items
			_EVENT_TYPES.update(enum.keys())
			_EVENT_TYPE_MAP.update({item.name.replace(" ", "_").upper(): key
									for key, item in enum.items()})

			del enum
			_EVENT_TYPE_MAP_EXTRA.update({
				"`": 'ACCENT_GRAVE',
				"*": 'NUMPAD_ASTERIX',
				"/": 'NUMPAD_SLASH',
				'+': 'NUMPAD_PLUS',
				"-": 'NUMPAD_MINUS',
				".": 'NUMPAD_PERIOD',
				"'": 'QUOTE',
				"RMB": 'RIGHTMOUSE',
				"LMB": 'LEFTMOUSE',
				"MMB": 'MIDDLEMOUSE',
			})
			_EVENT_TYPE_MAP_EXTRA.update({
				"%d" % i: "NUMPAD_%d" % i for i in range(10)
			})
		# done with once off init

		filter_text_split = filter_text.strip()
		filter_text_split = filter_text.split()

		# Modifier {kmi.attribute: name} mapping
		key_mod = {
			"ctrl": "ctrl",
			"alt": "alt",
			"shift": "shift",
			"cmd": "oskey",
			"oskey": "oskey",
			"any": "any",
		}
		# KeyMapItem like dict, use for comparing against
		# attr: {states, ...}
		kmi_test_dict = {}
		# Special handling of 'type' using a list if sets,
		# keymap items must match against all.
		kmi_test_type = []

		# initialize? - so if a if a kmi has a MOD assigned it wont show up.
		# for kv in key_mod.values():
		#	 kmi_test_dict[kv] = {False}

		# altname: attr
		for kk, kv in key_mod.items():
			if kk in filter_text_split:
				filter_text_split.remove(kk)
				kmi_test_dict[kv] = {True}

		# what's left should be the event type
		def kmi_type_set_from_string(kmi_type):
			kmi_type = kmi_type.upper()
			kmi_type_set = set()

			if kmi_type in _EVENT_TYPES:
				kmi_type_set.add(kmi_type)

			if not kmi_type_set or len(kmi_type) > 1:
				# replacement table
				for event_type_map in (_EVENT_TYPE_MAP, _EVENT_TYPE_MAP_EXTRA):
					kmi_type_test = event_type_map.get(kmi_type)
					if kmi_type_test is not None:
						kmi_type_set.add(kmi_type_test)
					else:
						# print("Unknown Type:", kmi_type)

						# Partial match
						for k, v in event_type_map.items():
							if (kmi_type in k) or (kmi_type in v):
								kmi_type_set.add(v)
			return kmi_type_set

		for i, kmi_type in enumerate(filter_text_split):
			kmi_type_set = kmi_type_set_from_string(kmi_type)

			if not kmi_type_set:
				return False

			kmi_test_type.append(kmi_type_set)
		# tiny optimization, sort sets so the smallest is first
		# improve chances of failing early
		kmi_test_type.sort(key=lambda kmi_type_set: len(kmi_type_set))

		# main filter func, runs many times
		def filter_func(kmi):
			for kk, ki in kmi_test_dict.items():
				val = getattr(kmi, kk)
				if val not in ki:
					return False

			# special handling of 'type'
			for ki in kmi_test_type:
				val = kmi.type
				if val == 'NONE' or val not in ki:
					# exception for 'type'
					# also inspect 'key_modifier' as a fallback
					val = kmi.key_modifier
					if not (val == 'NONE' or val not in ki):
						continue
					return False

			return True

	for km, kc in display_keymaps:
		km = km.active()
		layout.context_pointer_set("keymap", km)

		filtered_items = [kmi for kmi in km.keymap_items if filter_func(kmi)]

		if filtered_items:
			col = layout.column()

			row = col.row()
			row.label(text=km.name, icon='DOT')

			row.label()
			row.label()

			if km.is_user_modified:
				row.operator("preferences.keymap_restore", text="Restore")
			else:
				row.label()

			for kmi in filtered_items:
				draw_kmi(display_keymaps, kc, km, kmi, col, 1)
	return True

def draw_hierarchy(display_keymaps, layout):
	from bl_keymap_utils import keymap_hierarchy
	for entry in keymap_hierarchy.generate():
		draw_entry(display_keymaps, entry, layout)

def draw_keymaps(context, layout):
	from bl_keymap_utils.io import keyconfig_merge

	wm = context.window_manager
	kc_user = wm.keyconfigs.user
	kc_active = wm.keyconfigs.active
	spref = context.space_data

	# row.prop_search(wm.keyconfigs, "active", wm, "keyconfigs", text="Key Config")
	text = bpy.path.display_name(kc_active.name, has_ext=False)
	if not text:
		text = "Blender (default)"

	split = layout.split(factor=0.6)

	row = split.row()

	rowsub = row.row(align=True)

	rowsub.menu("USERPREF_MT_keyconfigs", text=text)
	rowsub.operator("wm.keyconfig_preset_add", text="", icon='ADD')
	rowsub.operator("wm.keyconfig_preset_add", text="", icon='REMOVE').remove_active = True

	rowsub = split.row(align=True)
	rowsub.operator("preferences.keyconfig_import", text="Import...", icon='IMPORT')
	rowsub.operator("preferences.keyconfig_export", text="Export...", icon='EXPORT')

	row = layout.row()
	col = layout.column()

	# layout.context_pointer_set("keyconfig", wm.keyconfigs.active)
	# row.operator("preferences.keyconfig_remove", text="", icon='X')
	rowsub = row.split(factor=0.4, align=True)
	# postpone drawing into rowsub, so we can set alert!

	layout.separator()
	display_keymaps = keyconfig_merge(kc_user, kc_user)
	filter_type = spref.filter_type
	filter_text = spref.filter_text.strip()
	
	global drawn_keymap_categories
	drawn_keymap_categories = []
	if filter_text:
		filter_text = filter_text.lower()
		ok = draw_filtered(display_keymaps, filter_type, filter_text, layout)
	else:
		draw_hierarchy(display_keymaps, layout)
		ok = True

	# go back and fill in rowsub
	rowsubsub = rowsub.row(align=True)
	rowsubsub.prop(spref, "filter_type", expand=True)
	rowsubsub = rowsub.row(align=True)
	if not ok:
		rowsubsub.alert = True
	rowsubsub.prop(spref, "filter_text", text="", icon='VIEWZOOM')

	if not filter_text:
		# When the keyconfig defines it's own preferences.
		kc_prefs = kc_active.preferences
		if kc_prefs is not None:
			box = col.box()
			row = box.row(align=True)

			pref = context.preferences
			keymappref = pref.keymap
			show_ui_keyconfig = keymappref.show_ui_keyconfig
			row.prop(
				keymappref,
				"show_ui_keyconfig",
				text="",
				icon='DISCLOSURE_TRI_DOWN' if show_ui_keyconfig else 'DISCLOSURE_TRI_RIGHT',
				emboss=False,
			)
			row.label(text="Preferences")

			if show_ui_keyconfig:
				# Defined by user preset, may contain mistakes out of our control.
				try:
					kc_prefs.draw(box)
				except Exception:
					import traceback
					traceback.print_exc()
			del box
		del kc_prefs

class KeyMapEntry(bpy.types.PropertyGroup):
	# A single HotkeyEditorPro keymap entry can mask several Blender keymaps. Not yet sure how to identify and store which ones are masked...
		# Probably just an external dictionary where the Keys are KeyMapEntry objects and the values are lists of bpy.types.KeyMapItem.
	idname: StringProperty()
	active: BoolProperty()
	#etc etc....
	# keymaps: CollectionProperty(type=bpy.types.KeyMapItem)

class KeyMapCategory(bpy.types.PropertyGroup):
	name: StringProperty(name="Category Name")
	warning: BoolProperty()						# Whether this category has a key conflict somewhere within it
	keymap_entries: CollectionProperty(type=KeyMapEntry)
	level: IntProperty(default=0)				# How nested this category is
	has_children: BoolProperty(default=False)	# Whether to draw the children drop-down arrow
	show_children: BoolProperty(default=True)	# This is the children drop-down arrow.
	parent_category: StringProperty()			# Name of the parent keymap category. (Cannot be an actual reference sadly)
	poll_description: StringProperty 			# A string to describe the poll function of this category.

# We define our own keymap category hierarchy, completely independent of that of Blender's.
keymap_category_hierarchy = {
	# Dictionaries contain dictionaries or lists
	# Lists contain strings.
	# Use empty dictionaries to represent strings at the dictionary level.
	"Window" : {
		"Window (Global)" : {},
		"3D View" : [
			"3D View (Global)",
			"Object Mode",
			"Mesh Edit Mode",
			"Curve Edit Mode",
			"Armature Edit Mode",
		],
		"Image Editor" : [
			"Image Editor (Global)",
			"UV Editor",
			"Image Paint",
			"Image Generic"
		]
	}
}

def create_keymap_categories_recursive(categories:bpy.props.CollectionProperty, string_dict, parent_name, level=0):
	# Populate the hotkey_categories CollectionProperty with entries. This should run once when the addon is enabled or after Blender has loaded. (TODO)
	for cat_name in string_dict.keys():
		entry = string_dict[cat_name]
		cat = categories.add()
		cat.name = cat_name
		cat.level = level
		cat.parent_category = parent_name
		if type(entry) == list:
			cat.has_children = True
			for child_name in entry:
				child_cat = categories.add()
				child_cat.name = child_name
				child_cat.level = level+1
				child_cat.parent_category = cat_name
		if type(entry) == dict:
			if len(entry)>0:
				cat.has_children = True
				create_keymap_categories_recursive(categories, entry, cat_name, level+1)

def create_keymap_hierarchy(string_hierarchy):
	"""Create a hierarchy of KeyMapCategory items based on the strings representing the categories' names."""
	wm = bpy.context.window_manager
	categories = wm.hotkey_categories
	categories.clear()
	create_keymap_categories_recursive(categories, string_hierarchy, parent_name="", level=0)

class HOTKEY_UL_hotkey_categories(bpy.types.UIList):
	def draw_filter(self, context, layout):
		# Nothing much to say here, it's usual UI code...
		row = layout.row()

		subrow = row.row(align=True)
		subrow.prop(self, "filter_name", text="")

	def filter_items(self, context, data, property):
		wm = data
		categories = wm.hotkey_categories

		filter_flags = []	# This could be several bits, but we'll just use all of them, since we just need one flag
		filter_neworder = range(len(categories))
		for c in categories:
			# Recursively check that all parents are enabled.
			child = c
			enabled = True
			while child and child.parent_category != "":
				parent_cat = categories.get(child.parent_category)
				if not parent_cat.show_children:
					enabled = False
				child = parent_cat

			if enabled:
				filter_flags.append(self.bitflag_filter_item)
			else:
				# If the parent category is disabled, don't draw this entry.
				filter_flags.append(0)
		
		# Preserve default filtering behaviour when it is used.
		helper_funcs = bpy.types.UI_UL_list
		if self.filter_name:
			filter_flags = helper_funcs.filter_items_by_name(self.filter_name, self.bitflag_filter_item, categories, "name",
														  reverse=self.use_filter_sort_reverse)

		return (filter_flags, filter_neworder)

	def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
		category = item

		if self.layout_type in {'DEFAULT', 'COMPACT'}:
			split = layout.split(factor=0.01+0.01*category.level)
			if category.has_children:
				icon = 'TRIA_DOWN' if category.show_children else 'TRIA_RIGHT'
				split.prop(category, 'show_children', icon=icon, text="", emboss=False)
			else:
				split.row()
			split.label(text=category.name)
		elif self.layout_type in {'GRID'}:
			layout.alignment = 'CENTER'
			layout.label(text="", icon_value=icon)

def draw_override(self, context):
	layout = self.layout
	wm = context.window_manager

	layout.prop(wm, 'use_custom_hotkey_editor')

	if not wm.use_custom_hotkey_editor:
		bpy.types.USERPREF_PT_keymap.draw_old(self, context)
		return
	
	layout.template_list(
		'HOTKEY_UL_hotkey_categories'
		,''
		,wm
		,'hotkey_categories'
		,wm
		,'active_hotkey_category_index'
		,rows = len(wm.hotkey_categories)
		,maxrows = len(wm.hotkey_categories)
	)

	# draw_keymaps(context, layout)
	# print(drawn_keymap_categories)

classes = [
	KeyMapEntry
	,KeyMapCategory
	,HOTKEY_UL_hotkey_categories
]

def initialize_hotkeys(self, context):
	create_keymap_hierarchy(keymap_category_hierarchy)

def register():
	from bpy.utils import register_class
	for c in classes:
		register_class(c)

	bpy.types.WindowManager.use_custom_hotkey_editor = BoolProperty(
		name		 = "Hotkey Editor Pro"
		,default	 = False
		,description = "Use the custom hotkey editor addon instead of the regular hotkey editor"
		,update		 = initialize_hotkeys
	)
	bpy.types.WindowManager.hotkey_categories = CollectionProperty(type=KeyMapCategory)
	bpy.types.WindowManager.active_hotkey_category_index = IntProperty()
	draw_old = bpy.types.USERPREF_PT_keymap.draw
	bpy.types.USERPREF_PT_keymap.draw_old = draw_old
	bpy.types.USERPREF_PT_keymap.draw = draw_override

def unregister():
	from bpy.utils import unregister_class
	for c in reversed(classes):
		unregister_class(c)

	bpy.types.USERPREF_PT_keymap.draw = bpy.types.USERPREF_PT_keymap.draw_old
	del bpy.types.USERPREF_PT_keymap.draw_old
	del bpy.types.WindowManager.use_custom_hotkey_editor
	del bpy.types.WindowManager.hotkey_categories


