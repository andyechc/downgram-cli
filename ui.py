"""
Módulo de interfaz de usuario usando Rich
Maneja la visualización de datos, tablas y selección interactiva
"""

from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn
from rich.text import Text
from rich.layout import Layout
import os
import time
from datetime import datetime, timedelta

console = Console()

class UserInterface:
    """Clase para manejar la interfaz de usuario con Rich"""
    
    @staticmethod
    def show_welcome():
        """Muestra el mensaje de bienvenida"""
        welcome_text = """
[bold cyan]🎬 Downgram CLI[/bold cyan]
[yellow]Una herramienta interactiva para filtrar y descargar videos de Telegram[/yellow]

[dim]Usando Telethon + Rich[/dim]
        """
        console.print(Panel(
            welcome_text,
            title="Bienvenido",
            border_style="cyan",
            padding=(1, 2)
        ))
    
    @staticmethod
    def show_channels_table(dialogs: List[Dict[str, Any]]) -> tuple[List[int], str]:
        """Muestra una tabla con los canales/grupos y permite selección múltiple. Retorna (indices, action)."""
        if not dialogs:
            console.print("[yellow]⚠️  No se encontraron canales o grupos[/yellow]")
            return [], 'exit'
        
        # Crear tabla
        table = Table(title="📺 Canales y Grupos Disponibles")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Tipo", style="magenta", width=8)
        table.add_column("Nombre", style="white", width=40)
        table.add_column("Participantes", style="green", width=12)
        
        # Agregar filas
        for i, dialog in enumerate(dialogs, 1):
            participants = dialog['participants']
            if participants == 'N/A':
                participants_text = "N/A"
            elif isinstance(participants, int):
                participants_text = f"{participants:,}"
            else:
                participants_text = str(participants)
            
            table.add_row(
                str(i),
                dialog['type'],
                dialog['title'][:37] + "..." if len(dialog['title']) > 37 else dialog['title'],
                participants_text
            )
        
        console.print(table)
        
        # Selección de canales
        console.print("\n[bold]📋 Selección de Canales[/bold]")
        console.print("[dim]Ingresa los números de los canales que deseas incluir en la búsqueda[/dim]")
        console.print("[dim]Ejemplo: 1,3,5-8,10 (separados por comas, rangos con guión)[/dim]")
        console.print("[dim]Escribe 'exit' para salir de la aplicación[/dim]")
        
        while True:
            try:
                selection_input = Prompt.ask("🎯 Selecciona canales", default="all")
                selection_input = selection_input.lower().strip()
                
                if selection_input == "exit":
                    return [], 'exit'
                
                if selection_input == "all":
                    return list(range(len(dialogs))), 'continue'
                
                selected_indices = UserInterface._parse_selection(selection_input, len(dialogs))
                
                if selected_indices:
                    console.print(f"[green]✅ Seleccionados {len(selected_indices)} canales[/green]")
                    return selected_indices, 'continue'
                else:
                    console.print("[red]❌ Selección inválida. Intenta nuevamente[/red]")
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️  Operación cancelada[/yellow]")
                return [], 'back'
    
    @staticmethod
    def _parse_selection(selection: str, max_index: int) -> List[int]:
        """Parsea una selección de usuarios (ej: 1,3,5-8,10)"""
        indices = []
        
        try:
            parts = selection.split(',')
            for part in parts:
                part = part.strip()
                
                if '-' in part:
                    # Rango (ej: 5-8)
                    start, end = map(int, part.split('-'))
                    indices.extend(range(start - 1, min(end, max_index)))
                else:
                    # Número individual
                    idx = int(part) - 1
                    if 0 <= idx < max_index:
                        indices.append(idx)
            
            return sorted(list(set(indices)))  # Eliminar duplicados y ordenar
            
        except ValueError:
            return []
    
    @staticmethod
    def get_search_keyword() -> tuple[str, str]:
        """Solicita la palabra clave para búsqueda. Retorna (keyword, action)."""
        console.print("\n[bold]🔍 Búsqueda de Videos[/bold]")
        console.print("[dim]Escribe 'back' para volver a la selección de canales[/dim]")
        
        while True:
            keyword = Prompt.ask("📝 Ingresa la palabra clave para buscar", default="")
            keyword = keyword.strip()
            
            if keyword.lower() == 'back':
                return '', 'back'
            
            if keyword:
                return keyword, 'continue'
            else:
                console.print("[red]❌ Debes ingresar una palabra clave[/red]")
    
    @staticmethod
    def show_search_results(search_result: Dict[str, Any]) -> tuple[List[int], bool]:
        """Muestra los resultados de búsqueda con paginación y permite selección"""
        media = search_result['media']
        current_page = search_result['current_page']
        total_pages = search_result['total_pages']
        total_found = search_result['total_found']
        has_more = search_result['has_more']
        
        if not media:
            console.print("[yellow]⚠️  No se encontraron archivos con esa palabra clave[/yellow]")
            return [], False
        
        # Crear tabla de resultados con información de paginación
        table = Table(title=f"� Resultados de Búsqueda - Página {current_page}/{total_pages} (Total: {total_found} archivos)")
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Tipo", style="green", width=6)
        table.add_column("Fecha", style="blue", width=12)
        table.add_column("Canal", style="magenta", width=15)
        table.add_column("Descripción", style="white", overflow="fold")
        table.add_column("Tamaño", style="yellow", width=10)
        
        # Agregar filas
        for i, item in enumerate(media, 1):
            # Formatear tamaño
            size = item['file_size']
            if size and isinstance(size, (int, float)) and size > 0:
                size_text = UserInterface._format_bytes(int(size))
            else:
                size_text = "N/A"
            
            # Formatear fecha a lenguaje humano
            date_text = UserInterface._format_human_date(item['date'])
            
            # Mostrar descripción: para audio usar título si está disponible, sino usar mensaje
            media_type = item.get('media_type', 'video')
            if media_type == 'audio' and item.get('title'):
                description = item['title']
            else:
                description = item['message'] or 'Sin descripción'
            
            # Truncar canal si es muy largo
            channel_name = item['channel_title']
            if len(channel_name) > 18:
                channel_name = channel_name[:18] + "..."
            
            # Determinar tipo de media
            media_type = item.get('media_type', 'video')
            if media_type == 'video':
                type_icon = "🎥 Vid"
            elif media_type == 'audio':
                type_icon = "🎵 Aud"
            elif media_type == 'voice':
                type_icon = "🎤 Voz"
            else:
                type_icon = "📁"
            
            table.add_row(
                str(i),
                type_icon,
                date_text,
                channel_name,
                description,
                size_text
            )
        
        console.print(table)
        
        # Mostrar información de paginación
        console.print(f"\n[bold]📄 Información de Página[/bold]")
        console.print(f"Página actual: {current_page}/{total_pages}")
        console.print(f"Archivos en esta página: {len(media)}")
        console.print(f"Total de archivos encontrados: {total_found}")
        
        # Selección de media con opciones de paginación
        console.print(f"\n[bold]📥 Selección de Archivos para Descargar[/bold]")
        console.print("[dim]Ingresa los números de los archivos que deseas descargar[/dim]")
        console.print("[dim]Opciones especiales:[/dim]")
        console.print("[dim]  • 'all' - descargar todos los archivos de esta página[/dim]")
        console.print("[dim]  • 'next' - ver siguiente página[/dim]")
        console.print("[dim]  • 'prev' - ver página anterior[/dim]")
        console.print("[dim]  • 'page N' - ir a página específica[/dim]")
        console.print("[dim]  • 'back' - volver a la búsqueda (cambiar palabra clave)[/dim]")
        
        while True:
            try:
                selection_input = Prompt.ask("🎯 Selecciona archivos o navega", default="")
                
                if not selection_input:
                    return [], False
                
                selection_input = selection_input.lower().strip()
                
                # Opción para volver atrás
                if selection_input == 'back':
                    return [], 'back'
                
                # Opciones de navegación
                if selection_input == 'next' and has_more:
                    return [], 'next'
                elif selection_input == 'next' and not has_more:
                    console.print("[yellow]⚠️  No hay más páginas disponibles[/yellow]")
                    continue
                elif selection_input == 'prev' and current_page > 1:
                    return [], 'prev'
                elif selection_input == 'prev' and current_page == 1:
                    console.print("[yellow]⚠️  Ya estás en la primera página[/yellow]")
                    continue
                elif selection_input.startswith('page '):
                    try:
                        page_num = int(selection_input.split(' ')[1])
                        if 1 <= page_num <= total_pages:
                            return [], f'page_{page_num}'
                        else:
                            console.print(f"[red]❌ Página inválida. Rango: 1-{total_pages}[/red]")
                    except (ValueError, IndexError):
                        console.print("[red]❌ Formato inválido. Usa: page N[/red]")
                    continue
                elif selection_input == 'all':
                    return list(range(len(media))), False
                
                # Selección normal de media
                selected_indices = UserInterface._parse_selection(selection_input, len(media))
                
                if selected_indices:
                    console.print(f"[green]✅ Seleccionados {len(selected_indices)} archivos para descargar[/green]")
                    return selected_indices, False
                else:
                    console.print("[red]❌ Selección inválida. Intenta nuevamente[/red]")
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️  Operación cancelada[/yellow]")
                return [], False
    
    @staticmethod
    def _format_human_date(date_str: str) -> str:
        """Formatea fecha a lenguaje humano (hace 2 horas, ayer, etc.)"""
        try:
            # Parsear la fecha del formato YYYY-MM-DD HH:MM
            video_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            now = datetime.now()
            
            # Calcular diferencia
            diff = now - video_date
            
            if diff < timedelta(minutes=1):
                return "Ahora"
            elif diff < timedelta(hours=1):
                minutes = int(diff.total_seconds() / 60)
                return f"Hace {minutes} min"
            elif diff < timedelta(hours=24):
                hours = int(diff.total_seconds() / 3600)
                return f"Hace {hours} h"
            elif diff < timedelta(days=2):
                if video_date.date() == now.date():
                    return "Hoy"
                else:
                    return "Ayer"
            elif diff < timedelta(days=7):
                days = diff.days
                return f"Hace {days} días"
            elif diff < timedelta(days=30):
                weeks = diff.days // 7
                return f"Hace {weeks} sem"
            elif diff < timedelta(days=365):
                months = diff.days // 30
                return f"Hace {months} mes"
            else:
                years = diff.days // 365
                return f"Hace {years} año" if years == 1 else f"Hace {years} años"
                
        except Exception:
            return date_str  # Si hay error, mostrar fecha original
    
    @staticmethod
    def _format_bytes(bytes_value: int) -> str:
        """Formatea bytes a formato legible (KB, MB, GB)"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} TB"
    
    @staticmethod
    def show_download_progress(videos: List[Dict[str, Any]], selected_indices: List[int]) -> None:
        """Muestra el progreso de descarga de videos"""
        selected_videos = [videos[i] for i in selected_indices]
        
        console.print(f"\n[bold]📥 Descargando {len(selected_videos)} videos...[/bold]")
        
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            
            tasks = {}
            
            for i, video in enumerate(selected_videos):
                # Crear nombre de archivo seguro
                channel_name = video['channel_title'][:30].replace('/', '_').replace('\\', '_')
                filename = f"video_{video['id']}_{channel_name}.mp4"
                
                # Crear tarea de progreso
                task_id = progress.add_task(
                    f"📹 {filename[:40]}...",
                    total=video.get('file_size', 0)
                )
                tasks[task_id] = video
            
            # Simular progreso (esto será reemplazado por el progreso real)
            import time
            for task_id, video in tasks.items():
                for i in range(100):
                    progress.update(task_id, advance=video.get('file_size', 1000000) // 100)
                    time.sleep(0.01)
                progress.update(task_id, completed=video.get('file_size', 0))
    
    @staticmethod
    def show_completion_message(downloaded_count: int, total_count: int):
        """Muestra mensaje de finalización"""
        if downloaded_count > 0:
            console.print(Panel(
                f"[green]✅ Descarga completada[/green]\n"
                f"Videos descargados: {downloaded_count}/{total_count}\n"
                f"Guardados en la carpeta 'downloads/'",
                title="Proceso Finalizado",
                border_style="green"
            ))
        else:
            console.print("[yellow]⚠️  No se descargaron videos[/yellow]")
    
    @staticmethod
    def show_error(message: str, title: str = "Error"):
        """Muestra un mensaje de error"""
        console.print(Panel(
            f"[red]❌ {message}[/red]",
            title=title,
            border_style="red"
        ))
    
    @staticmethod
    def confirm_action(message: str) -> bool:
        """Solicita confirmación al usuario"""
        return Confirm.ask(f"[yellow]⚠️  {message}[/yellow]")
    
    @staticmethod
    def select_download_folder(default_folder: str) -> str:
        """
        Permite al usuario seleccionar una carpeta de descarga personalizada.
        Retorna la ruta de la carpeta seleccionada o None para usar la por defecto.
        """
        console.print(f"\n[bold]📁 Carpeta de Descarga[/bold]")
        console.print(f"[dim]Carpeta por defecto: {default_folder}[/dim]")
        console.print("\n[dim]Opciones:[/dim]")
        console.print("[dim]  • Presiona Enter para usar la carpeta por defecto[/dim]")
        console.print("[dim]  • Escribe una ruta para usar una carpeta personalizada[/dim]")
        console.print("[dim]  • Escribe 'default' para usar la carpeta por defecto[/dim]")
        
        folder_input = Prompt.ask("📂 Ruta de descarga", default="")
        
        if not folder_input or folder_input.strip().lower() == 'default':
            return None  # Usar carpeta por defecto
        
        # Limpiar la ruta
        folder_path = folder_input.strip()
        
        # Expandir ~ a la carpeta home del usuario
        if folder_path.startswith('~'):
            folder_path = os.path.expanduser(folder_path)
        
        # Convertir a ruta absoluta
        folder_path = os.path.abspath(folder_path)
        
        # Verificar si la ruta es válida
        try:
            # Crear la carpeta si no existe
            os.makedirs(folder_path, exist_ok=True)
            console.print(f"[green]✅ Carpeta seleccionada: {folder_path}[/green]")
            return folder_path
        except Exception as e:
            console.print(f"[red]❌ Error con la ruta proporcionada: {e}[/red]")
            console.print(f"[yellow]⚠️  Se usará la carpeta por defecto: {default_folder}[/yellow]")
            return None
