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
from bpy.props import BoolProperty

# Some terminology notes, looking at rna_keymap_ui.py:
# A "KeyMap" is what I would rather call a KeyMap Category, eg. "Window", "3D View", etc.
# I may need to add some properties to this bpy.type, since I want to be able to set one of these as selected, or to show a warning icon.

# A "KeyMapItem" is a single shortcut. I may need to abstract this, since I want a single entry of my Shortcut concept to be able to represent several Blender shortcuts.

def my_draw_func(self, context):
	layout = self.layout
	wm = context.window_manager
	
	layout.prop(wm, 'use_custom_hotkey_editor')

	if not wm.use_custom_hotkey_editor:
		bpy.types.USERPREF_PT_keymap.draw_old(self, context)
		return

def register():
	bpy.types.WindowManager.use_custom_hotkey_editor = BoolProperty(
		name		 = "Hotkey Editor Pro"
		,default	 = True
		,description = "Use the custom hotkey editor addon instead of the regular hotkey editor"
	)

	draw_old = bpy.types.USERPREF_PT_keymap.draw
	bpy.types.USERPREF_PT_keymap.draw_old = draw_old
	bpy.types.USERPREF_PT_keymap.draw = my_draw_func

def unregister():
	bpy.types.USERPREF_PT_keymap.draw = bpy.types.USERPREF_PT_keymap.draw_old
	del bpy.types.USERPREF_PT_keymap.draw_old
	del bpy.types.WindowManager.use_custom_hotkey_editor


