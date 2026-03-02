# netLoginer_upc
本项目用于中国石油大学(华东)校园网自动登录
可实现自动化重连用于宿舍路由器、台式机等设备的无感重启
脚本利用python编写，已经测试过联通、电信可以正常使用

需要修改脚本中学号、密码、运营商部分
Linux用户可以使用Crontab实现开启自启动并维持检测

效果：

zeroiser@raspberrypi:~ $ crontab -l 

\# 每一小时的第5分钟，执行校园网登录脚本，并将输出日志记录到 login.log 文件
5 * * * * /home/zeroiser/upc_wifi/upc_login.py >> /home/zeroiser/upc_wifi/login.log 2>&1

\# 系统每次启动时，延迟1分钟后执行一次登录脚本，确保网络已准备就绪
@reboot sleep 30 && /home/zeroiser/upc_wifi/upc_login.py >> /home/zeroiser/upc_wifi/login.log 2>&1
