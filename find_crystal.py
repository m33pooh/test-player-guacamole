import state_bot
import cv2

frame = cv2.imread("crystal_dbl2.jpg")

prompt = (
    "Analyze this MMORPG game screenshot. "
    "Find the glowing BLUE Teleport Crystal object in the scene. "
    "The crystal is a tall blue glowing pillar/monument that players use to teleport to other zones. "
    "Reply ONLY with valid JSON: "
    '{"crystal_visible": true/false, '
    '"crystal_x": <int pixel x center of crystal in this image or null>, '
    '"crystal_y": <int pixel y center of crystal or null>, '
    '"crystal_description": "<brief where is it>"}'
)

result = state_bot.ask_vlm(frame, prompt, 200)
print("Result:", result)

# Also ask about the book icon on minimap
frame2 = cv2.imread("after_map_tab.jpg")
prompt2 = (
    "This is an MMORPG screenshot. In the TOP-RIGHT corner is the minimap. "
    "Below the minimap are two small clickable icons. "
    "What are these two icons and what are their approximate pixel coordinates in this image? "
    "Reply ONLY with valid JSON: "
    '{"icon1_x": <int>, "icon1_y": <int>, "icon1_label": "<what it does>", '
    '"icon2_x": <int>, "icon2_y": <int>, "icon2_label": "<what it does>"}'
)
result2 = state_bot.ask_vlm(frame2, prompt2, 250)
print("Minimap icons:", result2)
