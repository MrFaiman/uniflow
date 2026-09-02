package tests

import (
	"testing"

	"github.com/MrFaiman/uniflow/transfer"
)

func TestNormalizeRelativePathAcceptsNested(t *testing.T) {
	got, err := transfer.NormalizeRelativePath("a/b/c.txt")
	if err != nil {
		t.Fatal(err)
	}
	if got != "a/b/c.txt" && got != "a\\b\\c.txt" {
		t.Fatalf("unexpected normalized path %q", got)
	}
}

func TestNormalizeRelativePathRejectsTraversal(t *testing.T) {
	if _, err := transfer.NormalizeRelativePath("../etc/passwd"); err == nil {
		t.Fatal("expected error for .. segment")
	}
}

func TestNormalizeRelativePathRejectsAbsolute(t *testing.T) {
	if _, err := transfer.NormalizeRelativePath("/etc/passwd"); err == nil {
		t.Fatal("expected error for absolute path")
	}
}

func TestSafeJoinKeepsPathUnderBase(t *testing.T) {
	base := t.TempDir()
	got, err := transfer.SafeJoin(base, "nested/file.txt")
	if err != nil {
		t.Fatal(err)
	}
	if got == base {
		t.Fatal("expected nested path")
	}
}

func TestSafeJoinRejectsEscape(t *testing.T) {
	base := t.TempDir()
	if _, err := transfer.SafeJoin(base, "../outside.txt"); err == nil {
		t.Fatal("expected escape to be rejected")
	}
}
