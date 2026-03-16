__all__ = ["CBase64"]


class CBase64:
    """
    一个实现了固定非标准 Base64 编码和解码的静态工具类
    """

    _ALPHABET = "987XWVU6543zyx/wvro210nmlkji+hedFEDCcbaZYTSRQPutsONgfMLKqpJIHGBA"

    _PADDING_CHAR = "="

    assert len(set(_ALPHABET)) == 64, "字母表必须包含64个唯一的字符。"
    assert _PADDING_CHAR not in _ALPHABET, "填充字符不能出现在字母表中。"
    assert len(_PADDING_CHAR) == 1, "填充字符必须是单个字符。"

    _ENCODE_MAP = {i: char for i, char in enumerate(_ALPHABET)}
    _DECODE_MAP = {char: i for i, char in enumerate(_ALPHABET)}

    @staticmethod
    def encode(data: bytes) -> str:
        """
        使用固定的非标准字母表将 bytes 数据编码为 Base64 字符串

        :param data: 需要编码的原始二进制数据
        :return str: 编码后的字符串
        """
        encoded_chars = []
        data_len = len(data)

        for i in range(0, data_len, 3):
            chunk = data[i : i + 3]

            b1 = chunk[0]
            idx1 = b1 >> 2
            encoded_chars.append(CBase64._ENCODE_MAP[idx1])

            if len(chunk) > 1:
                b2 = chunk[1]
                idx2 = ((b1 & 0b11) << 4) | (b2 >> 4)
                encoded_chars.append(CBase64._ENCODE_MAP[idx2])

                if len(chunk) > 2:
                    b3 = chunk[2]
                    idx3 = ((b2 & 0b1111) << 2) | (b3 >> 6)
                    idx4 = b3 & 0b111111
                    encoded_chars.append(CBase64._ENCODE_MAP[idx3])
                    encoded_chars.append(CBase64._ENCODE_MAP[idx4])
                else:
                    idx3 = (b2 & 0b1111) << 2
                    encoded_chars.append(CBase64._ENCODE_MAP[idx3])
                    encoded_chars.append(CBase64._PADDING_CHAR)
            else:
                idx2 = (b1 & 0b11) << 4
                encoded_chars.append(CBase64._ENCODE_MAP[idx2])
                encoded_chars.append(CBase64._PADDING_CHAR * 2)

        return "".join(encoded_chars)

    @staticmethod
    def decode(encoded_str: str) -> bytes:
        """
        使用固定的非标准字母表将 Base64 字符串解码为 bytes 数据

        :param encoded_str: 需要解码的 Base64 字符串
        :return bytes: 解码后的原始二进制数据
        """
        num_padding = encoded_str.count(CBase64._PADDING_CHAR)
        if num_padding > 0:
            encoded_str = encoded_str[:-num_padding]

        decoded_bytes = bytearray()

        for i in range(0, len(encoded_str), 4):
            chunk = encoded_str[i : i + 4]
            try:
                val1 = CBase64._DECODE_MAP[chunk[0]]
                val2 = CBase64._DECODE_MAP[chunk[1]]

                b1 = (val1 << 2) | (val2 >> 4)
                decoded_bytes.append(b1)

                if len(chunk) > 2:
                    val3 = CBase64._DECODE_MAP[chunk[2]]
                    b2 = ((val2 & 0b1111) << 4) | (val3 >> 2)
                    decoded_bytes.append(b2)

                    if len(chunk) > 3:
                        val4 = CBase64._DECODE_MAP[chunk[3]]
                        b3 = ((val3 & 0b0011) << 6) | val4
                        decoded_bytes.append(b3)

            except KeyError as e:
                raise ValueError(f"输入字符串中包含无效的字符: {e}")

        return bytes(decoded_bytes)
