#!/bin/bash

# 安装必要的开发工具和库
sudo yum groupinstall -y "Development Tools"
sudo yum install -y wget python3-devel

# 下载并安装TA-Lib C库
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install

# 配置动态链接器
sudo echo "/usr/local/lib" >> /etc/ld.so.conf
sudo ldconfig

# 设置环境变量
echo "export TA_LIBRARY_PATH=/usr/lib" >> ~/.bashrc
echo "export TA_INCLUDE_PATH=/usr/include" >> ~/.bashrc
source ~/.bashrc

# 安装numpy（TA-Lib的依赖）
pip3 install numpy

# 安装TA-Lib Python包装器
pip3 install --no-binary TA-Lib TA-Lib

# 清理下载的文件
cd ..
rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
