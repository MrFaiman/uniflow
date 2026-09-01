package main

import (
	"encoding/binary"
	"io"
	"net"

	"google.golang.org/protobuf/proto"
)

// WriteProto marshals a message and writes its length-prefixed bytes to the connection
func WriteProto(conn net.Conn, msg proto.Message) error {
	data, err := proto.Marshal(msg)
	if err != nil {
		return err
	}

	// Write the length of the data as a uint32 (4 bytes)
	length := uint32(len(data))
	if err := binary.Write(conn, binary.LittleEndian, length); err != nil {
		return err
	}

	// Write the actual protobuf payload
	_, err = conn.Write(data)
	return err
}

// ReadProto reads the length prefix, then reads the exact payload into the message
func ReadProto(conn net.Conn, msg proto.Message) error {
	// Read the 4-byte length prefix
	var length uint32
	if err := binary.Read(conn, binary.LittleEndian, &length); err != nil {
		return err
	}

	// Read the exact amount of bytes specified by the length
	data := make([]byte, length)
	if _, err := io.ReadFull(conn, data); err != nil {
		return err
	}

	return proto.Unmarshal(data, msg)
}
