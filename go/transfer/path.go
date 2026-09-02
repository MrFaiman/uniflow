package transfer

import (
	"fmt"
	"path/filepath"
	"strings"
)

func NormalizeRelativePath(rel string) (string, error) {
	rel = strings.TrimSpace(rel)
	if rel == "" {
		return "", fmt.Errorf("relative path is empty")
	}
	if strings.HasPrefix(rel, "/") || filepath.IsAbs(rel) {
		return "", fmt.Errorf("relative path must not be absolute: %q", rel)
	}
	rel = strings.ReplaceAll(rel, "\\", "/")
	rel = strings.Trim(rel, "/")
	if rel == "" {
		return "", fmt.Errorf("relative path is empty")
	}
	parts := strings.Split(rel, "/")
	for _, part := range parts {
		if part == "" || part == "." {
			continue
		}
		if part == ".." {
			return "", fmt.Errorf("relative path must not contain ..: %q", rel)
		}
	}
	return filepath.FromSlash(rel), nil
}

func SafeJoin(baseDir, relativePath string) (string, error) {
	rel, err := NormalizeRelativePath(relativePath)
	if err != nil {
		return "", err
	}
	baseAbs, err := filepath.Abs(baseDir)
	if err != nil {
		return "", fmt.Errorf("resolve base dir: %w", err)
	}
	joined := filepath.Join(baseAbs, rel)
	joinedAbs, err := filepath.Abs(joined)
	if err != nil {
		return "", fmt.Errorf("resolve joined path: %w", err)
	}
	if joinedAbs != baseAbs && !strings.HasPrefix(joinedAbs, baseAbs+string(filepath.Separator)) {
		return "", fmt.Errorf("path escapes base dir: %q", relativePath)
	}
	return joinedAbs, nil
}
