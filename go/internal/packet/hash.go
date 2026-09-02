package packet

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"google.golang.org/protobuf/proto"

	"github.com/MrFaiman/uniflow/pb"
)

func CalculatePacketHash(packet *pb.FilePacket) (string, error) {
	copy := proto.Clone(packet).(*pb.FilePacket)
	copy.PacketHash = ""
	data, err := proto.MarshalOptions{Deterministic: true}.Marshal(copy)
	if err != nil {
		return "", fmt.Errorf("marshal packet: %w", err)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

func VerifyPacketHash(packetBytes []byte) (bool, error) {
	packet := &pb.FilePacket{}
	if err := proto.Unmarshal(packetBytes, packet); err != nil {
		return false, fmt.Errorf("unmarshal packet: %w", err)
	}
	if packet.PacketHash == "" {
		return false, nil
	}
	expected, err := CalculatePacketHash(packet)
	if err != nil {
		return false, err
	}
	return packet.PacketHash == expected, nil
}

func TargetReceiver(packetBytes []byte) (uint32, error) {
	packet := &pb.FilePacket{}
	if err := proto.Unmarshal(packetBytes, packet); err != nil {
		return 0, fmt.Errorf("unmarshal packet: %w", err)
	}
	return packet.TargetReceiver, nil
}
