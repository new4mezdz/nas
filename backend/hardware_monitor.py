# hardware_monitor.py
import requests
import json
import time

class HardwareMonitor:
    """OpenHardwareMonitor 数据获取类"""

    def __init__(self, ohm_url="http://localhost:8085", cache_duration=5):
        self.ohm_url = ohm_url.rstrip('/')
        self.cache_duration = cache_duration  # 缓存时间（秒）
        self._cache = None
        self._cache_time = 0

    def get_hardware_data(self):
        current_time = time.time()

        # 如果缓存有效，直接返回缓存数据
        if self._cache and (current_time - self._cache_time) < self.cache_duration:
            return self._cache

        # 否则获取新数据
        try:
            response = requests.get(f"{self.ohm_url}/data.json", timeout=2)
            response.raise_for_status()
            data = response.json()

            result = self._parse_ohm_data(data)

            # 更新缓存
            self._cache = result
            self._cache_time = current_time

            return result
        except Exception as e:
            print(f"[ERROR] 获取硬件数据失败: {e}")
            return self._cache  # 返回旧缓存（如果有）

    def _parse_ohm_data(self, data):
        """
        解析 OpenHardwareMonitor 返回的 JSON 数据
        提取温度、风扇转速、电压等信息
        """
        temperatures = []
        fans = []
        voltages = []

        # 递归遍历硬件树
        def traverse(node):
            if 'Children' in node:
                for child in node['Children']:
                    traverse(child)

            # 提取传感器数据
            if 'Text' in node and 'Value' in node:
                name = node['Text']
                value_str = node['Value']

                # 解析数值（去除单位）
                try:
                    if '°C' in value_str:
                        value = float(value_str.replace(' °C', ''))
                        temperatures.append({'name': name, 'value': value})
                    elif 'RPM' in value_str:
                        value = float(value_str.replace(' RPM', ''))
                        fans.append({'name': name, 'value': value})
                    elif 'V' in value_str and 'RPM' not in value_str:
                        value = float(value_str.replace(' V', ''))
                        voltages.append({'name': name, 'value': value})
                except ValueError:
                    pass

        # 开始遍历
        traverse(data)

        return {
            'temperatures': temperatures,
            'fans': fans,
            'voltages': voltages
        }


# 全局实例
hardware_monitor = HardwareMonitor()