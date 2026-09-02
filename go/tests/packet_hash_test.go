package tests

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"google.golang.org/protobuf/proto"

	"github.com/MrFaiman/uniflow/internal/packet"
	"github.com/MrFaiman/uniflow/pb"
)

type goldenFixture struct {
	PacketHash    string `json:"packet_hash"`
	SerializedHex string `json:"serialized_hex"`
}

func loadGolden(t *testing.T) goldenFixture {
	t.Helper()
	path := filepath.Join("testdata", "golden.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read golden: %v", err)
	}
	var fixture goldenFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("parse golden: %v", err)
	}
	return fixture
}

func TestCalculatePacketHashGoldenPython(t *testing.T) {
	fixture := loadGolden(t)
	data, err := hex.DecodeString(fixture.SerializedHex)
	if err != nil {
		t.Fatalf("decode golden: %v", err)
	}

	p := &pb.FilePacket{}
	if err := proto.Unmarshal(data, p); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	hash, err := packet.CalculatePacketHash(p)
	if err != nil {
		t.Fatalf("calculate: %v", err)
	}
	if hash != fixture.PacketHash {
		t.Fatalf("hash mismatch: got %s want %s", hash, fixture.PacketHash)
	}
}

func TestVerifyPacketHashGolden(t *testing.T) {
	fixture := loadGolden(t)
	data, err := hex.DecodeString(fixture.SerializedHex)
	if err != nil {
		t.Fatalf("decode golden: %v", err)
	}
	ok, err := packet.VerifyPacketHash(data)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if !ok {
		t.Fatal("expected valid packet hash")
	}
}

func TestTargetReceiver(t *testing.T) {
	fixture := loadGolden(t)
	data, err := hex.DecodeString(fixture.SerializedHex)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	target, err := packet.TargetReceiver(data)
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	if target != 1 {
		t.Fatalf("expected target 1, got %d", target)
	}
}

func TestVerifyPacketHashDetectsTamper(t *testing.T) {
	fixture := loadGolden(t)
	data, err := hex.DecodeString(fixture.SerializedHex)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	p := &pb.FilePacket{}
	if err := proto.Unmarshal(data, p); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(p.Data) > 0 {
		p.Data[0] ^= 0xff
	}
	tampered, err := proto.MarshalOptions{Deterministic: true}.Marshal(p)
	if err != nil {
		t.Fatalf("marshal tampered: %v", err)
	}

	ok, err := packet.VerifyPacketHash(tampered)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if ok {
		t.Fatal("expected invalid hash after tamper")
	}
}

func TestGoDeterministicSerializationMatchesPython(t *testing.T) {
	fixture := loadGolden(t)
	pythonBytes, err := hex.DecodeString(fixture.SerializedHex)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}

	p := &pb.FilePacket{}
	if err := proto.Unmarshal(pythonBytes, p); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	goBytes, err := proto.MarshalOptions{Deterministic: true}.Marshal(p)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if string(goBytes) != string(pythonBytes) {
		t.Fatalf("deterministic serialization mismatch between Go and Python")
	}
}
