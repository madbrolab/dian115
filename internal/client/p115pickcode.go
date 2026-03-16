package client

import (
	"fmt"
	"strings"
)

var (
	pickcodeAlphabet    = "0123456789abcdefghijklmnopqrstuvwxyz"
	prefixToTranstab    = map[string][36]byte{}
	prefixToTranstabRev = map[string]map[byte]byte{}
	prefixToFirstSuffix = map[string]byte{}
	firstSuffixToPrefix = map[byte]string{}
	alphabetIndex       = map[byte]int{}
)

func init() {
	for i := 0; i < len(pickcodeAlphabet); i++ {
		alphabetIndex[pickcodeAlphabet[i]] = i
	}
	set := func(prefix string, mapping string) {
		var table [36]byte
		for i := 0; i < 36; i++ {
			table[i] = mapping[i]
		}
		prefixToTranstab[prefix] = table
		rev := make(map[byte]byte, 36)
		for i := 0; i < 36; i++ {
			rev[table[i]] = pickcodeAlphabet[i]
		}
		prefixToTranstabRev[prefix] = rev
		prefixToFirstSuffix[prefix] = table[0]
	}

	set("a", "fuln1ytpj3smg8d5a094qh7cxkbi62zvewro")
	set("b", "sk721n9a0emlfpcrzbqdw3gjh6ty5xui48vo")
	set("c", "ywcz3hite6f1j0guoakvdb2ns7p8qr9ml5x4")
	set("d", "rq2vl5o7wsken9u8tp4jg3zbyc6xmhifd01a")
	set("e", "ljm9eqbcfhw7ktv3x1dgp5ua8y6s4znr2io0")
	set("fa", "fumk0ytpj3sng8d5a194qh7cxlbi62zvewro")
	set("fb", "sk732o9a1enmfpcrzbqdw4gjh6ty5xui08vl")
	set("fc", "ywcz6hite9f4j3gup2kvdb5osal0qr1nm8x7")
	set("fd", "on6vl0r2wpkeq9u3ts8jg7zbyc1xmhifd45a")
	set("fe", "ljm0es2cfhwakqv6x4dgp8r1by9u7znt5io3")

	for prefix, firstSuffix := range prefixToFirstSuffix {
		firstSuffixToPrefix[firstSuffix] = prefix
	}
}

func p115PickcodeToID(pickcode string) int64 {
	if pickcode == "" {
		return 0
	}
	var prefix string
	var cipher string
	if len(pickcode) >= 2 && pickcode[0] == 'f' {
		prefix = pickcode[:2]
		if len(pickcode) <= 6 {
			return 0
		}
		cipher = pickcode[2 : len(pickcode)-4]
	} else {
		prefix = pickcode[:1]
		if len(pickcode) <= 5 {
			return 0
		}
		cipher = pickcode[1 : len(pickcode)-4]
	}

	// Python的 pickcode_to_id 使用 PREFIX_TO_TRANSTAB_REV
	// 在Python中: PREFIX_TO_TRANSTAB = maketrans(scrambled, alphabet) → scrambled→alphabet
	//             PREFIX_TO_TRANSTAB_REV = reverse of above → alphabet→scrambled
	// 在Go中: prefixToTranstab[i] = scrambled[i] → alphabet_index→scrambled_char (即 alphabet→scrambled)
	//         prefixToTranstabRev[scrambled_char] = alphabet_char (即 scrambled→alphabet)
	// 所以 Python的REV = Go的prefixToTranstab
	table, ok := prefixToTranstab[prefix]
	if !ok {
		return 0
	}
	decoded := make([]byte, len(cipher))
	for i := 0; i < len(cipher); i++ {
		idx, ok := alphabetIndex[cipher[i]]
		if !ok {
			return 0
		}
		decoded[i] = table[idx]
	}
	return int64(b36decode(string(decoded)))
}

func p115GetStablePoint(pickcode string) string {
	if pickcode == "" {
		return ""
	}
	lenPick := len(pickcode)
	if lenPick < 4 {
		return strings.Repeat("0", 4-lenPick) + pickcode
	}
	var prefix string
	if lenPick >= 6 && pickcode[0] == 'f' {
		candidate := pickcode[:2]
		if _, ok := prefixToTranstab[candidate]; ok {
			prefix = candidate
		}
	}
	if prefix == "" && lenPick >= 5 {
		candidate := pickcode[:1]
		if _, ok := prefixToTranstab[candidate]; ok {
			prefix = candidate
		}
	}
	last4 := pickcode[lenPick-4:]
	if prefix == "" {
		if last4[0] == '0' {
			return last4
		}
		if p, ok := firstSuffixToPrefix[last4[0]]; ok {
			prefix = p
		} else {
			return ""
		}
	}
	// Python uses PREFIX_TO_TRANSTAB_REV which = Go's prefixToTranstab
	// But get_stable_point in Python uses PREFIX_TO_TRANSTAB_REV to translate last4
	// Wait - Python get_stable_point uses: pickcode[-4:].translate(transtab)
	// where transtab = PREFIX_TO_TRANSTAB_REV[prefix]
	// PREFIX_TO_TRANSTAB_REV maps alphabet→scrambled (Go's prefixToTranstab)
	// No wait - let me re-check:
	// Python PREFIX_TO_TRANSTAB = maketrans(scrambled, alphabet) → maps scrambled_char→alphabet_char
	// Python PREFIX_TO_TRANSTAB_REV = reverse → maps alphabet_char→scrambled_char
	// Python get_stable_point uses PREFIX_TO_TRANSTAB_REV → alphabet→scrambled
	// But that doesn't make sense for decryption...
	// Actually in Python get_stable_point:
	//   transtab = PREFIX_TO_TRANSTAB_REV[prefix]
	//   return pickcode[-4:].translate(transtab)
	// This translates the suffix using REV table
	// REV maps: 0→o, 1→n, etc (for fd prefix)
	// But the suffix is ciphertext, and we want plaintext (the stable point)
	// So REV is actually: alphabet_index→scrambled_char
	// Hmm, let me just use the same table as Python
	// Python REV = Go prefixToTranstab (both map alphabet→scrambled)
	table := prefixToTranstab[prefix]
	decoded := make([]byte, len(last4))
	for i := 0; i < len(last4); i++ {
		idx, ok := alphabetIndex[last4[i]]
		if !ok {
			return ""
		}
		decoded[i] = table[idx]
	}
	return string(decoded)
}

func p115IDToPickcode(id int64, stablePoint string, prefix string) (string, error) {
	if id < 0 {
		return "", fmt.Errorf("id不能为负数")
	}
	if stablePoint == "" {
		return "", fmt.Errorf("稳定点为空")
	}
	if prefix == "" {
		prefix = "a"
	}

	// stablePoint 是已经解码过的原始4字符不动点（由 p115GetStablePoint 返回）
	sp := stablePoint
	if len(sp) < 4 {
		sp = strings.Repeat("0", 4-len(sp)) + sp
	}
	if len(sp) > 4 {
		sp = sp[len(sp)-4:]
	}

	trans, ok := prefixToTranstab[prefix]
	if !ok {
		return "", fmt.Errorf("无效前缀: %s", prefix)
	}

	// 用目标前缀的转换表编码不动点
	suffix, ok := translateWithTable(sp, trans)
	if !ok {
		return "", fmt.Errorf("稳定点转换失败")
	}

	// 用目标前缀的转换表编码id
	mid, ok := translateWithTable(b36encode(id), trans)
	if !ok {
		return "", fmt.Errorf("id编码失败")
	}
	return prefix + mid + suffix, nil
}

func translateWithTable(src string, table [36]byte) (string, bool) {
	if src == "" {
		return "", true
	}
	out := make([]byte, len(src))
	for i := 0; i < len(src); i++ {
		idx, ok := alphabetIndex[src[i]]
		if !ok {
			return "", false
		}
		out[i] = table[idx]
	}
	return string(out), true
}

func translateWithMap(src string, trans map[byte]byte) string {
	if src == "" {
		return ""
	}
	out := make([]byte, len(src))
	for i := 0; i < len(src); i++ {
		v, ok := trans[src[i]]
		if !ok {
			return ""
		}
		out[i] = v
	}
	return string(out)
}

func b36encode(val int64) string {
	if val == 0 {
		return "0"
	}
	if val < 0 {
		return ""
	}
	var buf []byte
	for val > 0 {
		rest := val % 36
		buf = append(buf, pickcodeAlphabet[rest])
		val = val / 36
	}
	for i, j := 0, len(buf)-1; i < j; i, j = i+1, j-1 {
		buf[i], buf[j] = buf[j], buf[i]
	}
	return string(buf)
}

func b36decode(s string) int {
	val := 0
	for i := 0; i < len(s); i++ {
		c := s[i]
		var d int
		switch {
		case c >= '0' && c <= '9':
			d = int(c - '0')
		case c >= 'a' && c <= 'z':
			d = int(c-'a') + 10
		default:
			return 0
		}
		val = val*36 + d
	}
	return val
}
