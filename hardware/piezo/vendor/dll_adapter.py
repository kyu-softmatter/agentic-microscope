import ctypes
import struct
import sys

class DllAdapter:
	def __init__(self):
		self.dllFilename = ""
	
	def __del__(self):
		self.Uninit()
		if hasattr(self, "dllHandle"):
			del self.dllHandle
			
	def Init(self, dllFilename):
		self.dllFilename = dllFilename
		try:
			# Open DLL
			self.dllHandle = ctypes.cdll.LoadLibrary(dllFilename)
			
			# Set up argument and return types for DLL API functions
			self.dllHandle.Init.restype = ctypes.c_void_p
			self.dllHandle.Uninit.argtypes = [ctypes.c_void_p]
			self.dllHandle.GetDllVersion.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
			self.dllHandle.OpenSession.restype = ctypes.c_int
			self.dllHandle.OpenSession.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			self.dllHandle.CloseSession.argtypes = [ctypes.c_void_p]
			self.dllHandle.FindDevices.restype = ctypes.c_int
			self.dllHandle.FindDevices.argtypes = [ctypes.c_void_p]
			self.dllHandle.GetDevice.restype = ctypes.c_int
			self.dllHandle.GetDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetChannels.restype = ctypes.c_int
			self.dllHandle.GetChannels.argtypes = [ctypes.c_void_p]
			self.dllHandle.FindCommands.restype = ctypes.c_int
			self.dllHandle.FindCommands.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			self.dllHandle.GetCommand.restype = ctypes.c_int
			self.dllHandle.GetCommand.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandDescription.restype = ctypes.c_int
			self.dllHandle.GetCommandDescription.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandParameters.restype = ctypes.c_int
			self.dllHandle.GetCommandParameters.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			self.dllHandle.GetCommandParameterName.restype = ctypes.c_int
			self.dllHandle.GetCommandParameterName.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandParameterUnitsType.restype = ctypes.c_int
			self.dllHandle.GetCommandParameterUnitsType.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandParameterUnits.restype = ctypes.c_int
			self.dllHandle.GetCommandParameterUnits.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandResults.restype = ctypes.c_int
			self.dllHandle.GetCommandResults.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			self.dllHandle.GetCommandResultName.restype = ctypes.c_int
			self.dllHandle.GetCommandResultName.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandResultUnitsType.restype = ctypes.c_int
			self.dllHandle.GetCommandResultUnitsType.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetCommandResultUnits.restype = ctypes.c_int
			self.dllHandle.GetCommandResultUnits.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			
			# The DLL adapter does not currently provide hooks for enumerations.
			# Users can readily add this though, in which case the following functions
			# will be necessary.  Note that earlier versions of the DLL did not provide
			# these functions.
			#self.dllHandle.GetEnumerations.restype = ctypes.c_int
			#self.dllHandle.GetEnumerations.argtypes = [ctypes.c_void_p]
			#self.dllHandle.GetEnumerationName.restype = ctypes.c_int
			#self.dllHandle.GetEnumerationName.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			#self.dllHandle.GetEnumerationValues.restype = ctypes.c_int
			#self.dllHandle.GetEnumerationValues.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			#self.dllHandle.GetEnumerationValue.restype = ctypes.c_int
			#self.dllHandle.GetEnumerationValue.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			
			self.dllHandle.DoCommand.restype = ctypes.c_int
			self.dllHandle.DoCommand.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
			self.dllHandle.GetResultName.restype = ctypes.c_int
			self.dllHandle.GetResultName.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetResult.restype = ctypes.c_int
			self.dllHandle.GetResult.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetAllResultNames.restype = ctypes.c_int
			self.dllHandle.GetAllResultNames.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
			self.dllHandle.GetAllResults.restype = ctypes.c_int
			self.dllHandle.GetAllResults.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
			
			# Initialise DLL
			self.dllInstanceHandle = self.dllHandle.Init(None)
			return True
			
		except:
			if hasattr(self, "dllHandle"):
				delattr(self, "dllHandle")
			if hasattr(self, "dllInstanceHandle"):
				delattr(self, "dllInstanceHandle")
			return False

	def GetDevices(self):
		devices = []
		if hasattr(self, "dllInstanceHandle"):
			numDevices = self.dllHandle.FindDevices(self.dllInstanceHandle)
			index = 0
			while index < numDevices:
				# Definitely-too-small buffer initially
				tempArray = ctypes.create_string_buffer(2)
				# Find how big the buffer needs to be
				indexCtype = ctypes.c_int(index)
				sizeCtype = ctypes.c_int(1)
				stringSize = self.dllHandle.GetDevice(self.dllInstanceHandle, indexCtype, tempArray, sizeCtype)
				stringSize = stringSize + 1
				tempArray2 = ctypes.create_string_buffer(stringSize)
				stringSize = self.dllHandle.GetDevice(self.dllInstanceHandle, indexCtype, tempArray2, stringSize + 1)
				devices.append(tempArray2.value[:].decode("utf-8"))
				index = index + 1
		return devices
	
	def Uninit(self):
		if hasattr(self, "dllHandle") and hasattr(self, "dllInstanceHandle"):
			self.dllHandle.Uninit(self.dllInstanceHandle)
			delattr(self, "dllInstanceHandle");
	
	def OpenSession(self, deviceUrl):
		deviceUrlCtype = ctypes.c_char_p(deviceUrl.encode('utf-8'))
		self.currentDevice = deviceUrl
		if hasattr(self, "dllHandle"):
			value = self.dllHandle.OpenSession(self.dllInstanceHandle, deviceUrlCtype)
			if value == 0:
				delattr(self, "currentDevice")
		else:
			value = 0
		return bool(value)
	
	def CloseSession(self):
		self.dllHandle.CloseSession(self.dllInstanceHandle)
		if hasattr(self, "currentDevice"):
			delattr(self, "currentDevice")
	
	def IsSessionOpen(self):
		if hasattr(self, "dllInstanceHandle") and hasattr(self, "currentDevice"):
			return True
		else:
			return False
	
	def GetChannels(self):
		return []
	
	def GetDllVersion(self):
		majorVersion = ctypes.c_int(0)
		minorVersion = ctypes.c_int(0)
		buildVersion = ctypes.c_int(0)
		if hasattr(self, "dllHandle"):
			self.dllHandle.GetDllVersion(ctypes.byref(majorVersion), ctypes.byref(minorVersion), ctypes.byref(buildVersion))
		return (int(majorVersion.value), int(minorVersion.value), int(buildVersion.value))
	
	def DoCommand(self, command):
		commandCtype = ctypes.c_char_p(command.encode('utf-8'))
		numReturnValues = -2
		results = []
		if hasattr(self, "dllHandle") and hasattr(self, "dllInstanceHandle"):
			numReturnValues = self.dllHandle.DoCommand(self.dllInstanceHandle, commandCtype)

		if numReturnValues <= 0:
			if numReturnValues == -2:
				results = ["Connection not initialised"]
			elif numReturnValues == -4:
				results = ["Not enough parameters for command"]
			elif numReturnValues == -5:
				results = ["Comms link is broken"]
			elif numReturnValues == -11:
				results = ["Invalid command name"]
			else:
				results = ["Unknown return value " + str(numReturnValues)]
		else:
			tempArray = ctypes.create_string_buffer(2)
			
			sizeCtype = ctypes.c_int(1)
			stringSize = self.dllHandle.GetAllResultNames(self.dllInstanceHandle, tempArray, sizeCtype)
			stringSize = stringSize + 1
			tempArray2 = ctypes.create_string_buffer(stringSize)
			stringSize = self.dllHandle.GetAllResultNames(self.dllInstanceHandle, tempArray2, stringSize + 1)

			sizeCtype = ctypes.c_int(1)
			stringSize = self.dllHandle.GetAllResults(self.dllInstanceHandle, tempArray, sizeCtype)
			stringSize = stringSize + 1
			tempArray3 = ctypes.create_string_buffer(stringSize)
			stringSize = self.dllHandle.GetAllResults(self.dllInstanceHandle, tempArray3, stringSize + 1)
			
			namesList = tempArray2.value[:].decode("utf-8").splitlines()
			valuesList = tempArray3.value[:].decode("utf-8").splitlines()
			
			it1 = iter(namesList)
			it2 = iter(valuesList)
			try:
				while True:
					results.append((next(it1), next(it2)))
			except:
				pass
			
		return results
