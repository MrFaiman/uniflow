package main

//go:generate protoc --go_out=. --go_opt=module=github.com/MrFaiman/uniflow --go_opt=Mtransfer.proto=github.com/MrFaiman/uniflow/pb --go_opt=Mwire.proto=github.com/MrFaiman/uniflow/pb -I../proto ../proto/transfer.proto ../proto/wire.proto
