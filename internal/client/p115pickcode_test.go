package client

import (
	"fmt"
	"testing"
)

func TestPickcodeToID(t *testing.T) {
	// Known pair from listDir: cid=3214318650701905003, pc=fd0vyk328m963352fw
	pc := "fd0vyk328m963352fw"
	expectedID := int64(3214318650701905003)

	gotID := p115PickcodeToID(pc)
	fmt.Printf("pickcode=%s -> id=%d (expected=%d, match=%v)\n", pc, gotID, expectedID, gotID == expectedID)
	if gotID != expectedID {
		t.Errorf("p115PickcodeToID(%s) = %d, want %d", pc, gotID, expectedID)
	}

	// Test stable point
	sp := p115GetStablePoint(pc)
	fmt.Printf("stable_point=%s (expected=063d)\n", sp)
	if sp != "063d" {
		t.Errorf("p115GetStablePoint(%s) = %s, want 063d", pc, sp)
	}

	// Test file pickcodes
	pc2 := "d68c8nzu2jb3kxqlw"
	id2 := p115PickcodeToID(pc2)
	fmt.Printf("pickcode=%s -> id=%d\n", pc2, id2)

	pc3 := "cqbtg09pqqxjnd94k"
	id3 := p115PickcodeToID(pc3)
	fmt.Printf("pickcode=%s -> id=%d\n", pc3, id3)
}
