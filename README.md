# Azurlane Spine2d To Blender
本项目为开发stellaris模组时写的插件工具  
# 使用方法
1.通过unity反编译工具AssetStudio对游戏解包出的spine文件进行还原,通常会得到.png/.skel.asset/.atlas.asset文件,去掉.asset后缀  
2.将以上三个文件放入一个文件夹内,在spine软件内进行纹理解包,解包文件选择图集文件.atlas,解压到该文件夹  
3.在spine软件内导入数据,选择.skel文件导入,对不需要的图片进行清理后,导出数据,选择json格式  
4.打开blender,插件位于右侧t键栏中,加载json,导入blender成功  
# 注意事项
1.追加json功能用于合并多个.skel文件,并将两张图像合并为一张  
2.重载材质可以根据json和图集文件,匹配网格的命名数据重新加载纹理和uv数据  
3.删除无效顶点组会遍历选中的网格和骨骼,如果网格的部分顶点组名称在骨骼里找不到对应名称,则删除该顶点组  
4.补全空顶点组,当网格内的点数据不包含任何顶点组权重时,将会被赋予名称为"root"的顶点权重  
5.权重归一用于将选中网格的所有顶点保留一个小数点的方式权重总和归为1,例如0.2+0.3+0.5=1  
6.应用骨骼缩放用于骨骼缩放后对骨骼动画进行矫正,选中骨骼应用,并再次选中使用blender的ctrl+a全部变换  
# 导入Stellaris注意事项
1.Stellaris最大接受的骨骼数量为50个,超出会显示错误  
2.Stellaris最大纹理限制在6000*6000以下,超出会显示错误(没实际测试过上限)  
3.导入stellaris正确步骤:数据导入到blender-全选网格权重归一-删减骨骼数量-清除无效顶点组-补全空顶点组-对网格权重进行手动修复-应用骨骼缩放-全选应用全部变换通过pdx插件进行导出.mesh和.anim文件  
