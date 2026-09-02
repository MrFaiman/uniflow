package transfer

import (
	"encoding/binary"
	"io"
	"net"

	"google.golang.org/protobuf/proto"
)

func WriteProto(conn net.Conn, msg proto.Message) error {
	data, err := proto.Marshal(msg)
	if err != nil {
		return err
	}

	length := uint32(len(data))
	if err := binary.Write(conn, binary.LittleEndian, length); err != nil {
		return err
	}

	_, err = conn.Write(data)
	return err
}

func ReadProto(conn net.Conn, msg proto.Message) error {
	var length uint32
	if err := binary.Read(conn, binary.LittleEndian, &length); err != nil {
		return err
	}

	data := make([]byte, length)
	if _, err := io.ReadFull(conn, data); err != nil {
		return err
	}

	return proto.Unmarshal(data, msg)
}
