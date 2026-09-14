local cheatCode = [[
-- Murder Mystery 2 - PulseHub Style Menu
-- Modern UI with animations, tabs, smooth transitions

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local TweenService = game:GetService("TweenService")
local Camera = workspace.CurrentCamera
local LocalPlayer = Players.LocalPlayer
local Mouse = LocalPlayer:GetMouse()

local Config = {
    AimEnabled = true,
    SilentAim = true,
    FOV = 400,
    Smoothing = 0.12,
    ESPEnabled = true,
    ESPBox = true,
    ESPHealth = true,
    ESPNames = true,
    ESPDistance = true,
    ESPRole = true,
    ESPGun = true,
    AutoBlock = false,
    RapidClick = false,
    MaxDistance = 3000,
}

local Cache = {
    Drawings = {},
    Roles = {},
}

-- COLOR PALETTE (PulseHub style)
local Colors = {
    Primary = Color3.fromRGB(138, 43, 226), -- Purple
    Secondary = Color3.fromRGB(0, 255, 200), -- Cyan
    Dark = Color3.fromRGB(15, 15, 25),
    DarkAlt = Color3.fromRGB(25, 25, 40),
    Text = Color3.fromRGB(255, 255, 255),
    TextMuted = Color3.fromRGB(150, 150, 180),
    Red = Color3.fromRGB(255, 50, 80),
    Green = Color3.fromRGB(50, 200, 100),
}

-- ROLE DETECTION
local function GetPlayerRole(player)
    if not player or not player.Parent then return "Unknown" end
    local char = player.Character
    if not char then return "Unknown" end
    if char:FindFirstChild("Knife") or (char:FindFirstChildOfClass("Tool") and char:FindFirstChildOfClass("Tool").Name:lower():find("knife")) then
        return "Murderer"
    end
    if char:FindFirstChild("Gun") or char:FindFirstChild("Revolver") then
        return "Sheriff"
    end
    return "Innocent"
end

local function UpdateRoles()
    for _, player in pairs(Players:GetPlayers()) do
        if player ~= LocalPlayer then
            Cache.Roles[player.UserId] = GetPlayerRole(player)
        end
    end
end

-- GEOMETRY
local function WorldToScreen(pos)
    local screenPos, onScreen = Camera:WorldToScreenPoint(pos)
    return Vector2.new(screenPos.X, screenPos.Y), onScreen
end

local function Distance3D(pos1, pos2)
    return (pos1 - pos2).Magnitude
end

local function GetAimTarget()
    local closest = nil
    local closestDist = Config.FOV
    for _, player in pairs(Players:GetPlayers()) do
        if player == LocalPlayer or not player.Character then continue end
        local character = player.Character
        local hrp = character:FindFirstChild("HumanoidRootPart")
        local humanoid = character:FindFirstChild("Humanoid")
        if not hrp or not humanoid or humanoid.Health <= 0 then continue end
        local dist = Distance3D(Camera.CFrame.Position, hrp.Position)
        if dist > Config.MaxDistance then continue end
        local screenPos, onScreen = WorldToScreen(hrp.Position)
        if not onScreen then continue end
        local mousePos = Vector2.new(Mouse.X, Mouse.Y)
        local fovDist = (screenPos - mousePos).Magnitude
        if fovDist < closestDist then
            closestDist = fovDist
            closest = character
        end
    end
    return closest
end

-- AIM ENGINE
local AimConnection = nil
local function StartAimLoop()
    if AimConnection then AimConnection:Disconnect() end
    AimConnection = RunService.RenderStepped:Connect(function()
        if not Config.AimEnabled then return end
        local target = GetAimTarget()
        if target and Config.SilentAim then
            local hrp = target:FindFirstChild("HumanoidRootPart")
            local head = target:FindFirstChild("Head")
            if not hrp or not head then return end
            local myHrp = LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
            if not myHrp then return end
            local direction = (head.Position - myHrp.Position).Unit
            local smoothedDir = Camera.CFrame.LookVector:Lerp(direction, Config.Smoothing)
            Camera.CFrame = CFrame.new(Camera.CFrame.Position, Camera.CFrame.Position + smoothedDir)
        end
    end)
end

-- ESP ENGINE
local function CreateESPBox(player, character)
    if not Config.ESPBox then return end
    local key = player.UserId
    if Cache.Drawings[key] then
        for _, drawing in pairs(Cache.Drawings[key]) do
            pcall(function() drawing:Remove() end)
        end
    end
    Cache.Drawings[key] = {}
    
    local function MakeDrawing(type, props)
        local drawing = Drawing.new(type)
        for k, v in pairs(props) do
            pcall(function() drawing[k] = v end)
        end
        table.insert(Cache.Drawings[key], drawing)
    end
    
    local hrp = character:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    local screenPos, onScreen = WorldToScreen(hrp.Position)
    if not onScreen then return end
    local dist = Distance3D(Camera.CFrame.Position, hrp.Position)
    local boxSize = 2000 / dist * 40
    
    local color = Colors.Green
    local role = Cache.Roles[player.UserId] or "Unknown"
    if role == "Murderer" then color = Colors.Red elseif role == "Sheriff" then color = Color3.fromRGB(100, 150, 255) end
    
    MakeDrawing("Square", {
        Position = screenPos - Vector2.new(boxSize / 2, boxSize / 2),
        Size = Vector2.new(boxSize, boxSize),
        Color = color,
        Thickness = 3,
        Filled = false,
        Transparency = 0.7,
    })
    
    if Config.ESPHealth then
        local humanoid = character:FindFirstChild("Humanoid")
        if humanoid then
            local healthPct = math.max(0, humanoid.Health / humanoid.MaxHealth)
            MakeDrawing("Square", {
                Position = screenPos + Vector2.new(boxSize / 2 + 8, -boxSize / 2),
                Size = Vector2.new(5, boxSize * healthPct),
                Color = Color3.fromRGB(0, 255 * healthPct, 255 * (1 - healthPct)),
                Filled = true,
                Transparency = 0.5,
            })
        end
    end
    
    if Config.ESPRole then
        local role = Cache.Roles[player.UserId] or "?"
        MakeDrawing("Text", {
            Position = screenPos - Vector2.new(0, boxSize / 2 + 25),
            Text = "[" .. role .. "]",
            Size = 16,
            Color = Colors.Secondary,
            Center = true,
            Transparency = 0.8,
        })
    end
    
    if Config.ESPNames then
        MakeDrawing("Text", {
            Position = screenPos,
            Text = player.Name,
            Size = 15,
            Color = Colors.Text,
            Center = true,
            Transparency = 0.85,
        })
    end
    
    if Config.ESPDistance then
        MakeDrawing("Text", {
            Position = screenPos + Vector2.new(0, boxSize / 2 + 15),
            Text = string.format("%.0f m", dist / 5),
            Size = 13,
            Color = Colors.TextMuted,
            Center = true,
            Transparency = 0.8,
        })
    end
end

local ESPConnection = nil
local function StartESPLoop()
    if ESPConnection then ESPConnection:Disconnect() end
    ESPConnection = RunService.RenderStepped:Connect(function()
        if not Config.ESPEnabled then return end
        UpdateRoles()
        for _, player in pairs(Players:GetPlayers()) do
            if player == LocalPlayer or not player.Character then continue end
            local character = player.Character
            local humanoid = character:FindFirstChild("Humanoid")
            if not humanoid or humanoid.Health <= 0 then continue end
            local dist = Distance3D(Camera.CFrame.Position, character.HumanoidRootPart.Position)
            if dist > Config.MaxDistance then continue end
            CreateESPBox(player, character)
        end
    end)
end

-- ═══════════════════════════════════════════════════════════════════
-- UI: PULSEHUB STYLE
-- ═══════════════════════════════════════════════════════════════════

local ScreenGui = Instance.new("ScreenGui")
ScreenGui.Name = "MM2PulseUI"
ScreenGui.ResetOnSpawn = false
ScreenGui.ScreenInsets = Enum.ScreenInsets.CoreGui
ScreenGui.Parent = LocalPlayer:WaitForChild("PlayerGui")

-- MAIN MENU FRAME
local MainFrame = Instance.new("Frame")
MainFrame.Name = "MainMenu"
MainFrame.Size = UDim2.new(0, 500, 0, 650)
MainFrame.Position = UDim2.new(0.5, -250, 0.5, -325)
MainFrame.BackgroundColor3 = Colors.Dark
MainFrame.BorderSizePixel = 0
MainFrame.Visible = false
MainFrame.Parent = ScreenGui

-- Corner radius
local Corner = Instance.new("UICorner")
Corner.CornerRadius = UDim.new(0, 16)
Corner.Parent = MainFrame

-- Border
local BorderStroke = Instance.new("UIStroke")
BorderStroke.Color = Colors.Primary
BorderStroke.Thickness = 2
BorderStroke.Transparency = 0.5
BorderStroke.Parent = MainFrame

-- HEADER
local Header = Instance.new("Frame")
Header.Size = UDim2.new(1, 0, 0, 70)
Header.Position = UDim2.new(0, 0, 0, 0)
Header.BackgroundColor3 = Colors.DarkAlt
Header.BorderSizePixel = 0
Header.Parent = MainFrame

local HeaderCorner = Instance.new("UICorner")
HeaderCorner.CornerRadius = UDim.new(0, 16)
HeaderCorner.Parent = Header

-- GRADIENT BACKGROUND for header
local HeaderGradient = Instance.new("UIGradient")
HeaderGradient.Color = ColorSequence.new({
    ColorSequenceKeypoint.new(0, Colors.Primary),
    ColorSequenceKeypoint.new(1, Colors.Secondary)
})
HeaderGradient.Rotation = 90
HeaderGradient.Parent = Header

-- TITLE
local Title = Instance.new("TextLabel")
Title.Text = "MM2 CHEAT"
Title.Size = UDim2.new(0.7, 0, 1, 0)
Title.Position = UDim2.new(0.05, 0, 0, 0)
Title.BackgroundTransparency = 1
Title.TextColor3 = Colors.Text
Title.TextSize = 24
Title.Font = Enum.Font.GothamBold
Title.TextXAlignment = Enum.TextXAlignment.Left
Title.Parent = Header

-- VERSION
local Version = Instance.new("TextLabel")
Version.Text = "v3.0"
Version.Size = UDim2.new(0.25, 0, 1, 0)
Version.Position = UDim2.new(0.75, 0, 0, 0)
Version.BackgroundTransparency = 1
Version.TextColor3 = Colors.Secondary
Version.TextSize = 14
Version.Font = Enum.Font.GothamMedium
Version.TextXAlignment = Enum.TextXAlignment.Right
Version.Parent = Header

-- TAB BUTTONS
local TabFrame = Instance.new("Frame")
TabFrame.Size = UDim2.new(1, 0, 0, 50)
TabFrame.Position = UDim2.new(0, 0, 0, 70)
TabFrame.BackgroundColor3 = Colors.DarkAlt
TabFrame.BorderSizePixel = 0
TabFrame.Parent = MainFrame

local TabLayout = Instance.new("UIListLayout")
TabLayout.FillDirection = Enum.FillDirection.Horizontal
TabLayout.Padding = UDim.new(0, 0)
TabLayout.Parent = TabFrame

local tabs = {"AIM", "ESP", "AUTO", "SETTINGS"}
local tabButtons = {}
local contentFrames = {}

for i, tabName in ipairs(tabs) do
    local tabBtn = Instance.new("TextButton")
    tabBtn.Name = tabName
    tabBtn.Text = tabName
    tabBtn.Size = UDim2.new(0.25, 0, 1, 0)
    tabBtn.BackgroundColor3 = Colors.DarkAlt
    tabBtn.TextColor3 = i == 1 and Colors.Secondary or Colors.TextMuted
    tabBtn.TextSize = 13
    tabBtn.Font = Enum.Font.GothamMedium
    tabBtn.BorderSizePixel = 0
    tabBtn.Parent = TabFrame
    
    -- Bottom border for active tab
    local Underline = Instance.new("Frame")
    Underline.Size = UDim2.new(1, 0, 0, 3)
    Underline.Position = UDim2.new(0, 0, 1, -3)
    Underline.BackgroundColor3 = i == 1 and Colors.Secondary or Color3.fromRGB(50, 50, 70)
    Underline.BorderSizePixel = 0
    Underline.Parent = tabBtn
    
    tabButtons[i] = {btn = tabBtn, underline = Underline}
end

-- CONTENT AREA
local ContentScroll = Instance.new("ScrollingFrame")
ContentScroll.Name = "ContentScroll"
ContentScroll.Size = UDim2.new(1, 0, 1, -120)
ContentScroll.Position = UDim2.new(0, 0, 0, 120)
ContentScroll.BackgroundColor3 = Colors.Dark
ContentScroll.BorderSizePixel = 0
ContentScroll.ScrollBarThickness = 8
ContentScroll.ScrollBarImageColor3 = Colors.Primary
ContentScroll.TopImage = ""
ContentScroll.BottomImage = ""
ContentScroll.MidImage = "rbxasset://textures/ui/Core/scrollbar/Middle@2x.png"
ContentScroll.Parent = MainFrame

local ListLayout = Instance.new("UIListLayout")
ListLayout.Padding = UDim.new(0, 12)
ListLayout.Parent = ContentScroll

-- TOGGLE FUNCTION
local function CreateToggle(parent, label, getValue, setValue)
    local container = Instance.new("Frame")
    container.Size = UDim2.new(1, -20, 0, 50)
    container.Position = UDim2.new(0.05, 0, 0, 0)
    container.BackgroundColor3 = Colors.DarkAlt
    container.BorderSizePixel = 0
    container.Parent = parent
    
    local cornerRadius = Instance.new("UICorner")
    cornerRadius.CornerRadius = UDim.new(0, 10)
    cornerRadius.Parent = container
    
    local labelText = Instance.new("TextLabel")
    labelText.Text = label
    labelText.Size = UDim2.new(0.65, 0, 1, 0)
    labelText.Position = UDim2.new(0.05, 0, 0, 0)
    labelText.BackgroundTransparency = 1
    labelText.TextColor3 = Colors.Text
    labelText.TextSize = 14
    labelText.Font = Enum.Font.GothamMedium
    labelText.TextXAlignment = Enum.TextXAlignment.Left
    labelText.Parent = container
    
    local toggleBtn = Instance.new("TextButton")
    toggleBtn.Size = UDim2.new(0.25, 0, 0.6, 0)
    toggleBtn.Position = UDim2.new(0.7, 0, 0.2, 0)
    toggleBtn.BackgroundColor3 = getValue() and Colors.Green or Color3.fromRGB(80, 80, 100)
    toggleBtn.TextColor3 = Colors.Text
    toggleBtn.Text = getValue() and "ON" or "OFF"
    toggleBtn.TextSize = 12
    toggleBtn.Font = Enum.Font.GothamBold
    toggleBtn.BorderSizePixel = 0
    toggleBtn.Parent = container
    
    local toggleCorner = Instance.new("UICorner")
    toggleCorner.CornerRadius = UDim.new(0, 8)
    toggleCorner.Parent = toggleBtn
    
    toggleBtn.MouseButton1Click:Connect(function()
        setValue(not getValue())
        local newColor = getValue() and Colors.Green or Color3.fromRGB(80, 80, 100)
        toggleBtn.Text = getValue() and "ON" or "OFF"
        
        local tween = TweenService:Create(toggleBtn, TweenInfo.new(0.2), {BackgroundColor3 = newColor})
        tween:Play()
    end)
end

-- SLIDER FUNCTION
local function CreateSlider(parent, label, getValue, setValue, min, max)
    local container = Instance.new("Frame")
    container.Size = UDim2.new(1, -20, 0, 80)
    container.Position = UDim2.new(0.05, 0, 0, 0)
    container.BackgroundColor3 = Colors.DarkAlt
    container.BorderSizePixel = 0
    container.Parent = parent
    
    local cornerRadius = Instance.new("UICorner")
    cornerRadius.CornerRadius = UDim.new(0, 10)
    cornerRadius.Parent = container
    
    local labelText = Instance.new("TextLabel")
    labelText.Text = label .. ": " .. getValue()
    labelText.Size = UDim2.new(1, 0, 0, 25)
    labelText.Position = UDim2.new(0.05, 0, 0, 8)
    labelText.BackgroundTransparency = 1
    labelText.TextColor3 = Colors.Text
    labelText.TextSize = 13
    labelText.Font = Enum.Font.GothamMedium
    labelText.TextXAlignment = Enum.TextXAlignment.Left
    labelText.Parent = container
    
    local sliderBg = Instance.new("Frame")
    sliderBg.Size = UDim2.new(0.9, 0, 0, 6)
    sliderBg.Position = UDim2.new(0.05, 0, 0, 40)
    sliderBg.BackgroundColor3 = Color3.fromRGB(50, 50, 70)
    sliderBg.BorderSizePixel = 0
    sliderBg.Parent = container
    
    local sliderCorner = Instance.new("UICorner")
    sliderCorner.CornerRadius = UDim.new(0, 3)
    sliderCorner.Parent = sliderBg
    
    local fill = Instance.new("Frame")
    fill.Size = UDim2.new((getValue() - min) / (max - min), 0, 1, 0)
    fill.Position = UDim2.new(0, 0, 0, 0)
    fill.BackgroundColor3 = Colors.Secondary
    fill.BorderSizePixel = 0
    fill.Parent = sliderBg
    
    local fillCorner = Instance.new("UICorner")
    fillCorner.CornerRadius = UDim.new(0, 3)
    fillCorner.Parent = fill
    
    local function UpdateSlider(pos)
        pos = math.max(0, math.min(1, pos))
        local val = min + (max - min) * pos
        setValue(math.floor(val))
        fill.Size = UDim2.new(pos, 0, 1, 0)
        labelText.Text = label .. ": " .. getValue()
    end
    
    sliderBg.MouseButton1Down:Connect(function()
        local pos = (Mouse.X - sliderBg.AbsolutePosition.X) / sliderBg.AbsoluteSize.X
        UpdateSlider(pos)
        
        local connection
        connection = RunService.RenderStepped:Connect(function()
            if UserInputService:IsMouseButtonPressed(Enum.UserInputType.MouseButton1) then
                local pos = (Mouse.X - sliderBg.AbsolutePosition.X) / sliderBg.AbsoluteSize.X
                UpdateSlider(pos)
            else
                connection:Disconnect()
            end
        end)
    end)
end

-- BUILD TABS
-- AIM TAB
CreateToggle(ContentScroll, "Aim Enabled", function() return Config.AimEnabled end, function(v) Config.AimEnabled = v end)
CreateToggle(ContentScroll, "Silent Aim", function() return Config.SilentAim end, function(v) Config.SilentAim = v end)
CreateSlider(ContentScroll, "FOV", function() return Config.FOV end, function(v) Config.FOV = v end, 100, 600)
CreateSlider(ContentScroll, "Smoothing", function() return math.floor(Config.Smoothing * 100) end, function(v) Config.Smoothing = v / 100 end, 1, 50)

-- ESP TAB
CreateToggle(ContentScroll, "ESP Enabled", function() return Config.ESPEnabled end, function(v) Config.ESPEnabled = v end)
CreateToggle(ContentScroll, "Boxes", function() return Config.ESPBox end, function(v) Config.ESPBox = v end)
CreateToggle(ContentScroll, "Health", function() return Config.ESPHealth end, function(v) Config.ESPHealth = v end)
CreateToggle(ContentScroll, "Names", function() return Config.ESPNames end, function(v) Config.ESPNames = v end)
CreateToggle(ContentScroll, "Distance", function() return Config.ESPDistance end, function(v) Config.ESPDistance = v end)
CreateToggle(ContentScroll, "Roles", function() return Config.ESPRole end, function(v) Config.ESPRole = v end)
CreateToggle(ContentScroll, "Weapons", function() return Config.ESPGun end, function(v) Config.ESPGun = v end)

-- AUTO TAB
CreateToggle(ContentScroll, "Auto Block", function() return Config.AutoBlock end, function(v) Config.AutoBlock = v end)
CreateToggle(ContentScroll, "Rapid Click", function() return Config.RapidClick end, function(v) Config.RapidClick = v end)

-- SETTINGS TAB
CreateSlider(ContentScroll, "Max Distance", function() return Config.MaxDistance end, function(v) Config.MaxDistance = v end, 500, 5000)

-- FOOTER (Close button)
local Footer = Instance.new("Frame")
Footer.Size = UDim2.new(1, 0, 0, 50)
Footer.Position = UDim2.new(0, 0, 1, -50)
Footer.BackgroundColor3 = Colors.DarkAlt
Footer.BorderSizePixel = 0
Footer.Parent = MainFrame

local FooterCorner = Instance.new("UICorner")
FooterCorner.CornerRadius = UDim.new(0, 16)
FooterCorner.Parent = Footer

local CloseBtn = Instance.new("TextButton")
CloseBtn.Text = "CLOSE"
CloseBtn.Size = UDim2.new(0.9, 0, 0.7, 0)
CloseBtn.Position = UDim2.new(0.05, 0, 0.15, 0)
CloseBtn.BackgroundColor3 = Colors.Red
CloseBtn.TextColor3 = Colors.Text
CloseBtn.TextSize = 14
CloseBtn.Font = Enum.Font.GothamBold
CloseBtn.BorderSizePixel = 0
CloseBtn.Parent = Footer

local CloseCorner = Instance.new("UICorner")
CloseCorner.CornerRadius = UDim.new(0, 8)
CloseCorner.Parent = CloseBtn

CloseBtn.MouseButton1Click:Connect(function()
    MainFrame.Visible = false
end)

-- FLOAT BUTTON
local FloatBtn = Instance.new("TextButton")
FloatBtn.Name = "MenuToggle"
FloatBtn.Text = "CHEAT"
FloatBtn.Size = UDim2.new(0, 80, 0, 80)
FloatBtn.Position = UDim2.new(1, -100, 1, -100)
FloatBtn.BackgroundColor3 = Colors.Primary
FloatBtn.TextColor3 = Colors.Text
FloatBtn.TextSize = 14
FloatBtn.Font = Enum.Font.GothamBold
FloatBtn.BorderSizePixel = 0
FloatBtn.Parent = ScreenGui

local FloatCorner = Instance.new("UICorner")
FloatCorner.CornerRadius = UDim.new(0, 16)
FloatCorner.Parent = FloatBtn

-- Float button gradient
local FloatGradient = Instance.new("UIGradient")
FloatGradient.Color = ColorSequence.new({
    ColorSequenceKeypoint.new(0, Colors.Primary),
    ColorSequenceKeypoint.new(1, Colors.Secondary)
})
FloatGradient.Parent = FloatBtn

FloatBtn.MouseButton1Click:Connect(function()
    MainFrame.Visible = not MainFrame.Visible
    
    -- Pulse animation
local tween = TweenService:Create(FloatBtn, TweenInfo.new(0.2, Enum.EasingStyle.Back, Enum.EasingDirection.Out), {Size = UDim2.new(0, 85, 0, 85)})
    tween:Play()
    tween.Completed:Connect(function()
        local tween2 = TweenService:Create(FloatBtn, TweenInfo.new(0.1, Enum.EasingStyle.Back, Enum.EasingDirection.In), {Size = UDim2.new(0, 80, 0, 80)})
        tween2:Play()
    end)
end)

-- START LOOPS
StartAimLoop()
StartESPLoop()

print("[MM2 PulseHub Cheat] Loaded! Click CHEAT button to open")
]]

loadstring(cheatCode)()
