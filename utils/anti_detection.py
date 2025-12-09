import random
import asyncio
import math
from typing import Tuple

class HumanEmulation:
    """Simula comportamiento humano para evitar detección"""
    
    @staticmethod
    async def random_delay(min_ms: int = 800, max_ms: int = 3000) -> None:
        """Espera un tiempo aleatorio entre min_ms y max_ms"""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def human_typing(element, text: str, min_delay: int = 50, max_delay: int = 200) -> None:
        """Simula escritura humana con retrasos aleatorios entre caracteres"""
        for char in text:
            await element.type(char)
            await asyncio.sleep(random.uniform(min_delay / 1000, max_delay / 1000))
        
        # Pequeña pausa después de terminar de escribir
        await asyncio.sleep(random.uniform(0.3, 0.8))
    
    @staticmethod
    async def human_click(page, element) -> None:
        """Simula click humano con movimiento de mouse"""
        # Obtener posición del elemento
        box = await element.bounding_box()
        if not box:
            await element.click()
            return
        
        # Calcular punto de click con offset aleatorio
        x = box['x'] + random.uniform(5, box['width'] - 5)
        y = box['y'] + random.uniform(5, box['height'] - 5)
        
        # Simular movimiento de mouse desde posición aleatoria
        start_x = x + random.uniform(-200, 200)
        start_y = y + random.uniform(-200, 200)
        
        await page.mouse.move(start_x, start_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Mover mouse al objetivo con curva natural
        await HumanEmulation.move_mouse_naturally(page, start_x, start_y, x, y)
        
        # Pequeña pausa antes de hacer click
        await asyncio.sleep(random.uniform(0.1, 0.4))
        
        # Click con ligera variación de tiempo de presión
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()
        
        # Pequeña pausa después del click
        await asyncio.sleep(random.uniform(0.2, 0.6))
    
    @staticmethod
    async def move_mouse_naturally(page, start_x: float, start_y: float, end_x: float, end_y: float) -> None:
        """Mueve el mouse en una curva natural entre dos puntos"""
        steps = max(3, int(math.hypot(end_x - start_x, end_y - start_y) / 50))
        
        # Generar puntos de control para curva bézier
        control_x1 = start_x + random.uniform(-100, 100)
        control_y1 = start_y + random.uniform(-100, 100)
        control_x2 = end_x + random.uniform(-100, 100)
        control_y2 = end_y + random.uniform(-100, 100)
        
        for i in range(steps + 1):
            t = i / steps
            # Calcular punto en curva bézier cúbica
            x = ((1 - t) ** 3) * start_x + 3 * ((1 - t) ** 2) * t * control_x1 + 3 * (1 - t) * (t ** 2) * control_x2 + (t ** 3) * end_x
            y = ((1 - t) ** 3) * start_y + 3 * ((1 - t) ** 2) * t * control_y1 + 3 * (1 - t) * (t ** 2) * control_y2 + (t ** 3) * end_y
            
            await page.mouse.move(x, y)
            
            # Variar tiempo entre movimientos
            if i < steps:
                await asyncio.sleep(random.uniform(0.01, 0.05) * (1 + random.random()))
    
    @staticmethod
    async def human_scroll(page, amount: int = 200) -> None:
        """Simula scroll humano con variaciones naturales"""
        try:
            start_y = await page.evaluate('window.scrollY')
            target_y = start_y + amount
            
            # Dividir el scroll en múltiples pasos para parecer más humano
            steps = random.randint(3, 8)
            current_y = start_y
            
            for i in range(steps):
                # Calcular el siguiente punto con variación aleatoria
                progress = (i + 1) / steps
                eased_progress = progress * (2 - progress)  # easeOutQuint
                next_y = start_y + (target_y - start_y) * eased_progress
                
                # Añadir un poco de variación aleatoria al movimiento
                if i < steps - 1:
                    next_y += random.uniform(-20, 20)
                
                # Realizar el scroll parcial
                await page.evaluate(f'window.scrollTo(0, {next_y})')
                current_y = next_y
                
                # Tiempo de espera entre pasos con variación
                if i < steps - 1:
                    step_delay = random.uniform(0.05, 0.2) * (1 + random.random())
                    await asyncio.sleep(step_delay)
            
            # Pequeña pausa después del scroll completo
            await asyncio.sleep(random.uniform(0.3, 0.8))
            
        except Exception as e:
            print(f"HumanEmulation: Error en scroll humano: {e}")
            # Fallback: scroll simple pero con retraso humano
            await page.evaluate(f'window.scrollBy(0, {amount})')
            await asyncio.sleep(random.uniform(0.5, 1.5))