import asyncio
import math
import random


class HumanEmulation:
    """Simulación avanzada de comportamiento humano para evitar detección"""
    
    @staticmethod
    async def random_delay(min_ms: int = 800, max_ms: int = 4000) -> None:
        """Espera con retraso exponencial para parecer más humano"""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        variation = random.uniform(0.1, 0.3) * delay
        final_delay = delay + (variation if random.random() > 0.5 else -variation)
        
        for i in range(int(final_delay * 2)):
            await asyncio.sleep(0.5)
            if i % 2 == 0 and random.random() > 0.7:
                print(f"HumanEmulation: ⏳ Esperando... {i/2 + 0.5:.1f}/{final_delay:.1f} segundos")
        
        await asyncio.sleep(final_delay - (int(final_delay * 2) * 0.5))

    @staticmethod
    async def human_typing(element, text: str, min_delay: int = 80, max_delay: int = 250) -> None:
        """Simula escritura humana con errores y correcciones ocasionales"""
        try:
            for i, char in enumerate(text):
                # Simular errores ocasionales (5% de probabilidad)
                if random.random() < 0.05 and i > 2 and len(text) > 5:
                    wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz1234567890')
                    await element.type(wrong_char)
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await element.press('Backspace')
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                
                await element.type(char)
                
                # Variación de velocidad de escritura
                char_delay = random.uniform(min_delay / 1000, max_delay / 1000)
                if char in [' ', '.', ',', '@']:
                    char_delay *= 1.5  # Pausas más largas en espacios y puntuación
                
                await asyncio.sleep(char_delay)
            
            # Pequeña pausa después de terminar de escribir
            await asyncio.sleep(random.uniform(0.4, 1.2))
            
        except Exception as e:
            print(f"HumanEmulation: ❌ Error en escritura humana: {str(e)}")
            # Fallback: escribir todo el texto de una vez
            await element.fill(text)
            await asyncio.sleep(random.uniform(0.5, 1.0))

    @staticmethod
    async def human_click(page, element) -> None:
        """Simula click humano con movimiento de mouse natural y variación"""
        try:
            # Obtener posición del elemento
            box = await element.bounding_box()
            if not box:
                await element.click()
                return
            
            # Calcular punto de click con offset aleatorio
            click_x = box['x'] + random.uniform(10, box['width'] - 10)
            click_y = box['y'] + random.uniform(8, box['height'] - 8)
            
            # Simular movimiento de mouse desde posición aleatoria
            start_x = click_x + random.uniform(-300, 300)
            start_y = click_y + random.uniform(-300, 300)
            
            # Asegurar que las coordenadas estén dentro de la ventana
            viewport = await page.evaluate('''() => {
                return {width: window.innerWidth, height: window.innerHeight};
            }''')
            
            start_x = max(50, min(start_x, viewport['width'] - 50))
            start_y = max(50, min(start_y, viewport['height'] - 50))
            
            # Mover mouse a posición inicial
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # Mover mouse al objetivo con curva natural
            await HumanEmulation.move_mouse_naturally(page, start_x, start_y, click_x, click_y)
            
            # Pequeña pausa antes de hacer click
            await asyncio.sleep(random.uniform(0.15, 0.45))
            
            # Click con variación de tiempo de presión
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.08, 0.18))
            await page.mouse.up()
            
            # Pequeña pausa después del click
            await asyncio.sleep(random.uniform(0.25, 0.75))
            
        except Exception as e:
            print(f"HumanEmulation: ❌ Error en click humano: {str(e)}")
            # Fallback: click simple
            await element.click()
            await asyncio.sleep(random.uniform(0.3, 0.8))

    @staticmethod
    async def move_mouse_naturally(page, start_x: float, start_y: float, end_x: float, end_y: float) -> None:
        """Mueve el mouse en una curva natural entre dos puntos con variación aleatoria"""
        try:
            steps = max(4, int(math.hypot(end_x - start_x, end_y - start_y) / 60))
            
            # Generar puntos de control para curva bézier con variación aleatoria
            control_x1 = start_x + random.uniform(-150, 150)
            control_y1 = start_y + random.uniform(-150, 150)
            control_x2 = end_x + random.uniform(-150, 150)
            control_y2 = end_y + random.uniform(-150, 150)
            
            for i in range(steps + 1):
                t = i / steps
                
                # Aplicar función de easing para movimiento más natural
                eased_t = t * (2 - t)  # easeOutQuint
                
                # Calcular punto en curva bézier cúbica
                x = ((1 - eased_t) ** 3) * start_x + \
                    3 * ((1 - eased_t) ** 2) * eased_t * control_x1 + \
                    3 * (1 - eased_t) * (eased_t ** 2) * control_x2 + \
                    (eased_t ** 3) * end_x
                
                y = ((1 - eased_t) ** 3) * start_y + \
                    3 * ((1 - eased_t) ** 2) * eased_t * control_y1 + \
                    3 * (1 - eased_t) * (eased_t ** 2) * control_y2 + \
                    (eased_t ** 3) * end_y
                
                await page.mouse.move(x, y)
                
                # Tiempo de espera entre movimientos con variación
                if i < steps:
                    step_delay = random.uniform(0.02, 0.08) * (1 + random.random() * 0.5)
                    await asyncio.sleep(step_delay)
            
        except Exception as e:
            print(f"HumanEmulation: ❌ Error en movimiento de mouse natural: {str(e)}")
            # Fallback: mover directamente
            await page.mouse.move(end_x, end_y)
            await asyncio.sleep(random.uniform(0.1, 0.3))

    @staticmethod
    async def human_scroll(page, amount: int = 300) -> None:
        """Simula scroll humano con variaciones naturales y detección de contenido"""
        try:
            start_y = await page.evaluate('window.scrollY')
            target_y = start_y + amount
            
            # Dividir el scroll en múltiples pasos para parecer más humano
            steps = random.randint(4, 10)
            
            for i in range(steps):
                progress = (i + 1) / steps
                
                # Aplicar easing para movimiento más natural
                eased_progress = progress * (2 - progress)  # easeOutQuint
                
                next_y = start_y + (target_y - start_y) * eased_progress
                
                # Añadir variación aleatoria al movimiento
                if i < steps - 1:
                    next_y += random.uniform(-30, 30) * (1 - progress)
                
                # Realizar el scroll parcial
                await page.evaluate(f'window.scrollTo(0, {next_y})')
                
                # Tiempo de espera entre pasos con variación
                if i < steps - 1:
                    step_delay = random.uniform(0.08, 0.3) * (1 + random.random() * 0.7)
                    await asyncio.sleep(step_delay)
                
                # Simular lectura de contenido al hacer scroll
                if random.random() > 0.7 and i < steps - 2:
                    pause_duration = random.uniform(0.3, 1.2)
                    print(f"HumanEmulation: 👀 Simulando lectura durante {pause_duration:.1f} segundos...")
                    await asyncio.sleep(pause_duration)
            
            # Pequeña pausa después del scroll completo
            await asyncio.sleep(random.uniform(0.4, 1.0))
            
        except Exception as e:
            print(f"HumanEmulation: ❌ Error en scroll humano: {str(e)}")
            # Fallback: scroll simple pero con retraso humano
            await page.evaluate(f'window.scrollBy(0, {amount})')
            await asyncio.sleep(random.uniform(0.8, 2.0))
            
            # Simular interacción adicional
            if random.random() > 0.6:
                await asyncio.sleep(random.uniform(0.3, 0.8))
                viewport = await page.evaluate('''() => {
                    return {width: window.innerWidth, height: window.innerHeight};
                }''')
                random_x = random.randint(100, viewport['width'] - 100)
                random_y = random.randint(100, viewport['height'] - 100)
                await page.mouse.move(random_x, random_y, steps=random.randint(3, 8))
                await asyncio.sleep(random.uniform(0.2, 0.6))

        