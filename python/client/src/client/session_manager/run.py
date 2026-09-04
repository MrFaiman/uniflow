from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from client.common.config import get_socket_path
from client.session_manager.listener import listen_to_receivers
from client.session_manager.manager import SessionManager
from client.supervisor import ReceiverSupervisor


def process_messages(
    manager: SessionManager,
    messages: Queue,
    supervisor: ReceiverSupervisor,
) -> None:
    while True:
        supervisor.check()
        try:
            message = messages.get(timeout=0.5)
        except Empty:
            continue
        manager.handle_serialized_packet(message)


def run_session_manager(output_folder: Path) -> None:
    output_folder = output_folder.resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    manager = SessionManager(output_folder)
    messages: Queue = Queue(maxsize=10000)
    stop_event = Event()
    ready_event = Event()
    socket_path = get_socket_path()

    listener_thread = Thread(
        target=listen_to_receivers,
        args=(socket_path, messages, stop_event, ready_event),
        daemon=True,
    )
    listener_thread.start()

    if not ready_event.wait(timeout=5):
        raise RuntimeError("Session Manager IPC socket did not become ready")

    supervisor = ReceiverSupervisor()

    try:
        supervisor.start()
        print(f"Receiving files into: {output_folder}", flush=True)
        process_messages(manager, messages, supervisor)
    except KeyboardInterrupt:
        print("Stopping Session Manager", flush=True)
    finally:
        supervisor.stop()
        stop_event.set()
        listener_thread.join(timeout=2)
        socket_path.unlink(missing_ok=True)
