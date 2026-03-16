package client

import (
	"bytes"
	"encoding/base64"
	"math/big"
)

var (
	p115Gkts = []byte{
		0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8,
		0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa,
		0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6,
		0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7,
		0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86,
		0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81,
		0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48,
		0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e,
		0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5,
	}
	p115Modulus = func() *big.Int {
		v, _ := new(big.Int).SetString("8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683", 16)
		return v
	}()
	p115Exponent = big.NewInt(0x10001)
)

func p115Encrypt(data []byte) ([]byte, error) {
	xorText := make([]byte, 16)
	tmp := p115Xor(data, []byte{0x8d, 0xa5, 0xa5, 0x8d})
	reverseBytes(tmp)
	xorText = append(xorText, p115Xor(tmp, []byte{0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18, 0x4c, 0x01, 0x3f, 0x46})...)

	cipherData := make([]byte, 0, ((len(xorText)+116)/117)*128)
	for offset := 0; offset < len(xorText); offset += 117 {
		end := offset + 117
		if end > len(xorText) {
			end = len(xorText)
		}
		block := xorText[offset:end]
		padded := p115PadPKCS1v15(block)
		c := new(big.Int).Exp(padded, p115Exponent, p115Modulus)
		out := c.Bytes()
		if len(out) < 128 {
			pad := make([]byte, 128-len(out))
			out = append(pad, out...)
		}
		cipherData = append(cipherData, out...)
	}
	encoded := make([]byte, base64.StdEncoding.EncodedLen(len(cipherData)))
	base64.StdEncoding.Encode(encoded, cipherData)
	return encoded, nil
}

func p115Decrypt(cipherData []byte) ([]byte, error) {
	decoded := make([]byte, base64.StdEncoding.DecodedLen(len(cipherData)))
	n, err := base64.StdEncoding.Decode(decoded, cipherData)
	if err != nil {
		return nil, err
	}
	decoded = decoded[:n]

	data := make([]byte, 0, len(decoded))
	for offset := 0; offset < len(decoded); offset += 128 {
		end := offset + 128
		if end > len(decoded) {
			end = len(decoded)
		}
		block := decoded[offset:end]
		p := new(big.Int).Exp(new(big.Int).SetBytes(block), p115Exponent, p115Modulus)
		b := p.Bytes()
		idx := bytes.IndexByte(b, 0)
		if idx >= 0 && idx+1 < len(b) {
			data = append(data, b[idx+1:]...)
		} else {
			data = append(data, b...)
		}
	}

	if len(data) < 16 {
		return nil, nil
	}
	keyL := p115GenKey(data[:16], 12)
	tmp := p115Xor(data[16:], keyL)
	reverseBytes(tmp)
	return p115Xor(tmp, []byte{0x8d, 0xa5, 0xa5, 0x8d}), nil
}

func p115PadPKCS1v15(message []byte) *big.Int {
	length := len(message)
	padLen := 126 - length
	if padLen < 0 {
		padLen = 0
	}
	buf := make([]byte, 0, 2+padLen+1+length)
	buf = append(buf, 0x00)
	buf = append(buf, bytes.Repeat([]byte{0x02}, padLen)...)
	buf = append(buf, 0x00)
	buf = append(buf, message...)
	return new(big.Int).SetBytes(buf)
}

func p115GenKey(randKey []byte, skLen int) []byte {
	xorKey := make([]byte, skLen)
	length := skLen * (skLen - 1)
	index := 0
	for i := 0; i < skLen && i < len(randKey); i++ {
		x := int(randKey[i]) + int(p115Gkts[index])
		xorKey[i] = p115Gkts[length] ^ byte(x&0xff)
		length -= skLen
		index += skLen
	}
	return xorKey
}

func p115Xor(src []byte, key []byte) []byte {
	if len(src) == 0 {
		return []byte{}
	}
	res := make([]byte, 0, len(src))
	keyLen := len(key)
	i := len(src) & 0b11
	if i > 0 {
		res = append(res, p115BytesXor(src[:i], key[:i])...)
	}
	for j := i; j < len(src); {
		end := j + keyLen
		if end > len(src) {
			end = len(src)
		}
		res = append(res, p115BytesXor(src[j:end], key[:end-j])...)
		j = end
	}
	return res
}

func p115BytesXor(v1 []byte, v2 []byte) []byte {
	out := make([]byte, len(v1))
	for i := range v1 {
		out[i] = v1[i] ^ v2[i]
	}
	return out
}

func reverseBytes(b []byte) {
	for i, j := 0, len(b)-1; i < j; i, j = i+1, j-1 {
		b[i], b[j] = b[j], b[i]
	}
}
