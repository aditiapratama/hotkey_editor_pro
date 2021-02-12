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

User Modified/Created flags handling
Blender keeps track of whether a keymap was created by the user, existed but was modified by the user, or is a default Blender keymap.
On one hand, this would be nice to keep, on the other hand, maybe the fact that our hotkey editor builds on top of Blender's is enough.

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

_EVENT_TYPES = set()
_EVENT_TYPE_MAP = {}
_EVENT_TYPE_MAP_EXTRA = {}

def get_HEP_category(blender_category_name):
	# If this Blender hotkey category (bpy.types.KeyMap) is mapped to a HEP category, return that HEP category (name, for now)
	for k in custom_to_blender_category_mapping.keys():
		if blender_category_name in custom_to_blender_category_mapping[k]:
			return k

def draw_km(display_keymaps, kc, km, children, level):
	km = km.active()	# NOTE: This seems to do nothing.

	HEP_category = get_HEP_category(km.name)

	name = km.name
	if children and not HEP_category:
		# Put the Parent key map's entries in a 'global' sub-category
		# equal in hierarchy to the other children categories
		name = iface_("%s (Global)") % km.name
		HEP_category = get_HEP_category(name)
	
	if not HEP_category:
		HEP_category = name

	if HEP_category not in category_to_kmi.keys():
		category_to_kmi[HEP_category] = []

	# Key Map items
	for kmi in km.keymap_items:
		category_to_kmi[HEP_category].append(kmi)

	# Child key maps
	if children:
		for entry in children:
			draw_entry(display_keymaps, entry, level + 1)

def draw_entry(display_keymaps, entry, level=0):
	idname, spaceid, regionid, children = entry

	for km, kc in display_keymaps:
		if km.name == idname and km.space_type == spaceid and km.region_type == regionid:
			draw_km(display_keymaps, kc, km, children, level)

def draw_hierarchy(display_keymaps):
	from bl_keymap_utils import keymap_hierarchy
	for entry in keymap_hierarchy.generate():
		draw_entry(display_keymaps, entry)

def draw_keymaps(context):
	from bl_keymap_utils.io import keyconfig_merge

	wm = context.window_manager
	kc_user = wm.keyconfigs.user

	display_keymaps = keyconfig_merge(kc_user, kc_user)	# TODO: Is this doing anything??
	draw_hierarchy(display_keymaps)

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

# Also define which of our keymap categories correspond to which Blender keymap categories.
# Matching names implicitly belong with each other, so they don't need to be specified.
custom_to_blender_category_mapping = {
	"Object Mode" : ["Object Mode (Global)"],
	"Mesh Edit Mode" : ["Mesh"],
	"Curve Edit Mode" : ["Curve"],
	"Armature Edit Mode" : ["Armature"],
}

category_to_kmi = {}

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
	
	split = layout.split(factor=0.3)
	split.row().template_list(
		'HOTKEY_UL_hotkey_categories'
		,''
		,wm
		,'hotkey_categories'
		,wm
		,'active_hotkey_category_index'
		,rows = len(wm.hotkey_categories)
		,maxrows = len(wm.hotkey_categories)
	)

	col = split.column()
	categories = wm.hotkey_categories
	active_HEP_cat = categories[wm.active_hotkey_category_index]

	if active_HEP_cat.name in category_to_kmi:
		hotkeys = category_to_kmi[active_HEP_cat.name]
		for hotkey in hotkeys:
			col.row().label(text=hotkey.idname)
	else:
		print("Category not found: " + active_HEP_cat.name)

classes = [
	KeyMapEntry
	,KeyMapCategory
	,HOTKEY_UL_hotkey_categories
]

def initialize_hotkeys(self, context):
	create_keymap_hierarchy(keymap_category_hierarchy)

	draw_keymaps(context)
	# for k in category_to_kmi.keys():
	# 	print(k)

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


