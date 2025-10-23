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
        提取温度、风扇转速、电压、功耗等信息
        """
        temperatures = []
        fans = []
        voltages = []
        powers = []
        clocks = []
        disks_temp = []
        memory_load = None  # 新增：内存使用率

        # 递归遍历硬件树
        def traverse(node, parent_type=''):
            nonlocal memory_load  # 声明使用外部变量

            # 判断节点类型
            node_text = node.get('Text', '')
            if 'HDD' in node_text or 'SSD' in node_text or 'NVMe' in node_text or 'SATA' in node_text:
                parent_type = 'disk'

            if 'Children' in node:
                for child in node['Children']:
                    traverse(child, parent_type)

            # 提取传感器数据
            if 'Text' in node and 'Value' in node:
                name = node['Text']
                value_str = node['Value']

                # 解析数值（去除单位）
                try:
                    if '°C' in value_str:
                        value = float(value_str.replace(' °C', ''))
                        temp_data = {'name': name, 'value': value}

                        if parent_type == 'disk':
                            disks_temp.append(temp_data)
                        else:
                            temperatures.append(temp_data)
                    elif 'RPM' in value_str:
                        value = float(value_str.replace(' RPM', ''))
                        fans.append({'name': name, 'value': value})
                    elif ' W' in value_str:
                        value = float(value_str.replace(' W', ''))
                        powers.append({'name': name, 'value': value})
                    elif 'MHz' in value_str:
                        value = float(value_str.replace(' MHz', ''))
                        clocks.append({'name': name, 'value': value})
                    elif '%' in value_str:  # 新增：解析百分比（内存使用率）
                        value = float(value_str.replace(' %', ''))
                        # 判断是否为内存负载
                        if 'Memory' in name or 'RAM' in name or 'Load' in name:
                            memory_load = value
                    elif 'V' in value_str and 'RPM' not in value_str and 'MHz' not in value_str:
                        value = float(value_str.replace(' V', ''))
                        voltages.append({'name': name, 'value': value})
                except ValueError:
                    pass

        # 开始遍历
        traverse(data)

        return {
            'temperatures': temperatures,
            'fans': fans,
            'voltages': voltages,
            'powers': powers,
            'clocks': clocks,
            'disks_temp': disks_temp,
            'memory_load': memory_load  # 新增：返回内存使用率
        }


# 全局实例
hardware_monitor = HardwareMonitor()