import DefaultTable
import struct

tsi0Format = '>HHl'

def fixlongs((glyphID, textLength, textOffset)):
	return int(glyphID), int(textLength), textOffset	


class table_T_S_I__0(DefaultTable.DefaultTable):
	
	dependencies = ["TSI1"]
	
	def decompile(self, data, ttFont):
		numGlyphs = ttFont['maxp'].numGlyphs
		indices = []
		size = struct.calcsize(tsi0Format)
		for i in range(numGlyphs + 5):
			glyphID, textLength, textOffset = fixlongs(struct.unpack(tsi0Format, data[:size]))
			indices.append((glyphID, textLength, textOffset))
			data = data[size:]
		assert len(data) == 0
		assert indices[-5] == (0XFFFE, 0, -1409540300), "bad magic number"  # 0xABFC1F34
		self.indices = indices[:-5]
		self.extra_indices = indices[-4:]
	
	def compile(self, ttFont):
		if not hasattr(self, "indices"):
			# We have no corresponging table (TSI1 or TSI3); let's return
			# no data, which effectively means "ignore us".
			return ""
		data = ""
		for index, textLength, textOffset in self.indices:
			data = data + struct.pack(tsi0Format, index, textLength, textOffset)
		data = data + struct.pack(tsi0Format, 0XFFFE, 0, -1409540300)  # 0xABFC1F34
		for index, textLength, textOffset in self.extra_indices:
			data = data + struct.pack(tsi0Format, index, textLength, textOffset)
		return data
	
	def set(self, indices, extra_indices):
		# gets called by 'TSI1' or 'TSI3'
		self.indices = indices
		self.extra_indices = extra_indices
	
	def toXML(self, writer, ttFont):
		writer.comment("This table will be calculated by the compiler")
		writer.newline()

