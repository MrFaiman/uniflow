package chaos

import (
	"fmt"
	"math/rand"
	"net"
	"strconv"
	"sync"
)

type Config struct {
	Loss        float64
	BitFlip     float64
	Misroute    float64
	Seed        int64
	ListenPorts []int
	DestPorts   []int
	DestHost    string
	ListenIP    string
}

type Relay struct {
	cfg      Config
	sendConn *net.UDPConn
	destAddr map[int]*net.UDPAddr
	rng      *rand.Rand
	mu       sync.Mutex
}

func NewRelay(cfg Config) (*Relay, error) {
	if cfg.ListenIP == "" {
		cfg.ListenIP = "127.0.0.1"
	}
	if cfg.DestHost == "" {
		cfg.DestHost = "127.0.0.1"
	}
	if cfg.Seed == 0 {
		cfg.Seed = 1
	}
	if len(cfg.ListenPorts) == 0 {
		return nil, fmt.Errorf("listen ports required")
	}
	if len(cfg.DestPorts) == 0 {
		cfg.DestPorts = append([]int(nil), cfg.ListenPorts...)
	}
	if len(cfg.ListenPorts) != len(cfg.DestPorts) {
		return nil, fmt.Errorf("listen and dest port counts must match")
	}

	sendConn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: 0})
	if err != nil {
		return nil, err
	}

	destAddr := make(map[int]*net.UDPAddr, len(cfg.DestPorts))
	for _, port := range cfg.DestPorts {
		addr, err := net.ResolveUDPAddr("udp", net.JoinHostPort(cfg.DestHost, strconv.Itoa(port)))
		if err != nil {
			_ = sendConn.Close()
			return nil, err
		}
		destAddr[port] = addr
	}

	return &Relay{
		cfg:      cfg,
		sendConn: sendConn,
		destAddr: destAddr,
		rng:      rand.New(rand.NewSource(cfg.Seed)),
	}, nil
}

func (r *Relay) Start() ([]*net.UDPConn, error) {
	listeners := make([]*net.UDPConn, 0, len(r.cfg.ListenPorts))
	for i, port := range r.cfg.ListenPorts {
		conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP(r.cfg.ListenIP), Port: port})
		if err != nil {
			for _, l := range listeners {
				_ = l.Close()
			}
			return nil, err
		}
		listeners = append(listeners, conn)
		go r.serve(conn, i)
	}
	return listeners, nil
}

func (r *Relay) Close() {
	_ = r.sendConn.Close()
}

func (r *Relay) serve(conn *net.UDPConn, listenIndex int) {
	buf := make([]byte, 65535)
	for {
		n, _, err := conn.ReadFromUDP(buf)
		if err != nil {
			return
		}
		data := append([]byte(nil), buf[:n]...)
		r.forward(data, listenIndex)
	}
}

func (r *Relay) forward(data []byte, listenIndex int) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.rng.Float64() < r.cfg.Loss {
		return
	}
	if r.rng.Float64() < r.cfg.BitFlip && len(data) > 0 {
		idx := r.rng.Intn(len(data))
		bit := uint(r.rng.Intn(8))
		data[idx] ^= 1 << bit
	}

	destIndex := listenIndex
	if r.rng.Float64() < r.cfg.Misroute && len(r.cfg.DestPorts) > 1 {
		candidates := make([]int, 0, len(r.cfg.DestPorts)-1)
		for i := range r.cfg.DestPorts {
			if i != listenIndex {
				candidates = append(candidates, i)
			}
		}
		destIndex = candidates[r.rng.Intn(len(candidates))]
	}

	targetPort := r.cfg.DestPorts[destIndex]
	addr := r.destAddr[targetPort]
	_, _ = r.sendConn.WriteToUDP(data, addr)
}
