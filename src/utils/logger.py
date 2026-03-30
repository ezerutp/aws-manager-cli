"""Operations Logger Module - Logs dump and recreate operations"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict


class OperationsLogger:
    """Handles logging for dump download and database recreate operations"""
    
    def __init__(self):
        """Initialize the logger with config directory"""
        self.config_dir = Path.home() / ".config" / "aws-manager"
        self.logs_dir = self.config_dir / "logs"
        self._ensure_logs_directory()
    
    def _ensure_logs_directory(self):
        """Create logs directory if it doesn't exist"""
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"⚠ Advertencia: No se pudo crear directorio de logs: {e}")
    
    def _get_current_datetime_info(self) -> dict:
        """Get current date and time information"""
        now = datetime.now()
        
        # Get day name in Spanish
        days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        day_name = days[now.weekday()]
        
        return {
            'fecha': now.strftime('%Y-%m-%d'),
            'hora': now.strftime('%H:%M:%S'),
            'dia': day_name,
            'timestamp': now.isoformat()
        }
    
    def log_dump_download(self, dump_name: str, environment: str, 
                          file_size_mb: Optional[float] = None) -> bool:
        """
        Log a dump download operation
        
        Args:
            dump_name: Name of the downloaded dump file
            environment: Environment from which the dump was downloaded
            file_size_mb: Size of the dump file in MB (optional)
        
        Returns:
            True if logged successfully, False otherwise
        """
        try:
            log_file = self.logs_dir / "dump_operations.log"
            datetime_info = self._get_current_datetime_info()
            
            log_entry = {
                'operacion': 'DESCARGA_DUMP',
                'nombre_dump': dump_name,
                'entorno_origen': environment,
                'fecha': datetime_info['fecha'],
                'hora': datetime_info['hora'],
                'dia': datetime_info['dia'],
                'timestamp': datetime_info['timestamp']
            }
            
            if file_size_mb is not None:
                log_entry['tamaño_mb'] = file_size_mb
            
            # Append to log file
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
            return True
            
        except Exception as e:
            print(f"⚠ Advertencia: No se pudo registrar en log: {e}")
            return False
    
    def log_database_recreate(self, dump_name: str, database_name: str, 
                              environment: str, duration_seconds: float,
                              file_size_mb: Optional[float] = None) -> bool:
        """
        Log a database recreate operation
        
        Args:
            dump_name: Name of the dump file used
            database_name: Name of the database that was recreated
            environment: Original environment of the dump
            duration_seconds: Time taken to complete the operation
            file_size_mb: Size of the dump file in MB (optional)
        
        Returns:
            True if logged successfully, False otherwise
        """
        try:
            log_file = self.logs_dir / "recreate_operations.log"
            datetime_info = self._get_current_datetime_info()
            
            # Format duration in a human-readable way
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            
            log_entry = {
                'operacion': 'RECREAR_BASE_DATOS',
                'nombre_dump': dump_name,
                'base_datos': database_name,
                'entorno_origen': environment,
                'fecha': datetime_info['fecha'],
                'hora': datetime_info['hora'],
                'dia': datetime_info['dia'],
                'duracion_segundos': round(duration_seconds, 2),
                'duracion_legible': duration_str,
                'timestamp': datetime_info['timestamp']
            }
            
            if file_size_mb is not None:
                log_entry['tamaño_mb'] = file_size_mb
            
            # Append to log file
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
            return True
            
        except Exception as e:
            print(f"⚠ Advertencia: No se pudo registrar en log: {e}")
            return False
    
    def get_recent_dumps(self, limit: int = 10) -> list:
        """Get recent dump download operations"""
        try:
            log_file = self.logs_dir / "dump_operations.log"
            if not log_file.exists():
                return []
            
            entries = []
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            
            # Return most recent entries
            return entries[-limit:] if len(entries) > limit else entries
            
        except Exception as e:
            print(f"⚠ Error al leer logs: {e}")
            return []
    
    def get_recent_recreates(self, limit: int = 10) -> list:
        """Get recent database recreate operations"""
        try:
            log_file = self.logs_dir / "recreate_operations.log"
            if not log_file.exists():
                return []
            
            entries = []
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            
            # Return most recent entries
            return entries[-limit:] if len(entries) > limit else entries
            
        except Exception as e:
            print(f"⚠ Error al leer logs: {e}")
            return []
    
    def get_logs_directory(self) -> Path:
        """Get the logs directory path"""
        return self.logs_dir
    
    def print_recent_dumps(self, limit: int = 10):
        """Print recent dump operations in a readable format"""
        entries = self.get_recent_dumps(limit)
        
        if not entries:
            print("No hay registros de descargas de dumps.")
            return
        
        print(f"\n{'='*80}")
        print(f"ÚLTIMAS {len(entries)} DESCARGAS DE DUMPS")
        print(f"{'='*80}\n")
        
        for entry in entries:
            print(f"📦 {entry.get('nombre_dump', 'N/A')}")
            print(f"   Entorno:  {entry.get('entorno_origen', 'N/A')}")
            print(f"   Fecha:    {entry.get('dia', 'N/A')}, {entry.get('fecha', 'N/A')} a las {entry.get('hora', 'N/A')}")
            if 'tamaño_mb' in entry:
                print(f"   Tamaño:   {entry['tamaño_mb']} MB")
            print()
    
    def print_recent_recreates(self, limit: int = 10):
        """Print recent recreate operations in a readable format"""
        entries = self.get_recent_recreates(limit)
        
        if not entries:
            print("No hay registros de recreaciones de base de datos.")
            return
        
        print(f"\n{'='*80}")
        print(f"ÚLTIMAS {len(entries)} RECREACIONES DE BASE DE DATOS")
        print(f"{'='*80}\n")
        
        for entry in entries:
            print(f"🔄 {entry.get('nombre_dump', 'N/A')} → {entry.get('base_datos', 'N/A')}")
            print(f"   Entorno:  {entry.get('entorno_origen', 'N/A')}")
            print(f"   Fecha:    {entry.get('dia', 'N/A')}, {entry.get('fecha', 'N/A')} a las {entry.get('hora', 'N/A')}")
            print(f"   Duración: {entry.get('duracion_legible', 'N/A')} ({entry.get('duracion_segundos', 0)} segundos)")
            if 'tamaño_mb' in entry:
                print(f"   Tamaño:   {entry['tamaño_mb']} MB")
            print()
    
    @staticmethod
    def get_all_logs() -> List[Dict]:
        """Get all logs from both dump and recreate operations, combined and sorted.
        
        Returns:
            List of all log entries
        """
        config_dir = Path.home() / ".config" / "aws-manager" / "logs"
        all_logs = []
        
        # Read dump logs
        dump_log_file = config_dir / "dump_operations.log"
        if dump_log_file.exists():
            try:
                with open(dump_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            entry['_log_type'] = 'dump'
                            all_logs.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"Error al leer dump logs: {e}")
        
        # Read recreate logs
        recreate_log_file = config_dir / "recreate_operations.log"
        if recreate_log_file.exists():
            try:
                with open(recreate_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            entry['_log_type'] = 'recreate'
                            all_logs.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"Error al leer recreate logs: {e}")
        
        return all_logs
    
    @staticmethod
    def display_logs(limit: Optional[int] = None):
        """Display all logs in a git log style format, ordered from newest to oldest.
        
        Args:
            limit: Maximum number of logs to display. If None, show all logs.
        """
        config_dir = Path.home() / ".config" / "aws-manager" / "logs"
        
        if not config_dir.exists():
            print("\n✗ No hay logs disponibles todavía.")
            print("Los logs se crearán automáticamente cuando realices operaciones de dump o recreate.\n")
            return
        
        all_logs = OperationsLogger.get_all_logs()
        
        if not all_logs:
            print("\n✗ No hay logs disponibles.\n")
            return
        
        # Sort by timestamp (newest first)
        logs_sorted = sorted(all_logs, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        if limit:
            logs_sorted = logs_sorted[:limit]
        
        # Display in git log style
        OperationsLogger._display_logs_git_style(logs_sorted, len(all_logs), limit)
    
    @staticmethod
    def _display_logs_git_style(logs_sorted: List[Dict], total_logs: int, limit: Optional[int]):
        """Display logs in git log style format"""
        
        # Color codes for terminal (ANSI)
        YELLOW = '\033[33m'
        BLUE = '\033[36m'
        GREEN = '\033[32m'
        RESET = '\033[0m'
        BOLD = '\033[1m'
        
        for log in logs_sorted:
            log_type = log.get('_log_type', '')
            timestamp_str = log.get('timestamp', '')
            
            # Parse timestamp for display
            try:
                dt = datetime.fromisoformat(timestamp_str)
                # Format similar to git: "Sat Mar 28 07:31:51 2026 -0500"
                date_display = dt.strftime('%a %b %d %H:%M:%S %Y %z')
                if not date_display.endswith('-0500') and not date_display.endswith('+'):
                    date_display += ' -0500'
            except:
                date = log.get('fecha', 'N/A')
                time = log.get('hora', 'N/A')
                weekday = log.get('dia', 'N/A')
                date_display = f"{weekday} {date} {time}"
            
            # Display based on operation type
            if log_type == 'dump':
                operation_type = "DESCARGA_DUMP"
                dump_name = log.get('nombre_dump', 'N/A')
                environment = log.get('entorno_origen', 'N/A')
                
                print(f"{YELLOW}operacion {operation_type} {timestamp_str}{RESET}")
                print(f"Dump:     {dump_name}")
                print(f"Entorno:  {environment}")
                print(f"Fecha:    {date_display}")
                
                if 'tamaño_mb' in log:
                    print(f"Tamaño:   {log['tamaño_mb']:.1f} MB")
                
                print(f"\n    Descarga de dump desde {environment}")
                
            elif log_type == 'recreate':
                operation_type = "RECREAR_BASE_DATOS"
                dump_name = log.get('nombre_dump', 'N/A')
                database = log.get('base_datos', 'N/A')
                duration = log.get('duracion_legible', 'N/A')
                
                print(f"{YELLOW}operacion {operation_type} {timestamp_str}{RESET}")
                print(f"Dump:     {dump_name}")
                print(f"Database: {database}")
                print(f"Fecha:    {date_display}")
                print(f"Duración: {duration}")
                
                if 'tamaño_mb' in log:
                    print(f"Tamaño:   {log['tamaño_mb']:.1f} MB")
                
                print(f"\n    Recreación de base de datos '{database}' desde dump '{dump_name}'")
            
            print()  # Empty line between entries
        
        # Summary at the end
        print(f"Mostrando {len(logs_sorted)} operaciones", end='')
        if limit and total_logs > limit:
            print(f" (de {total_logs} totales)")
        else:
            print()
